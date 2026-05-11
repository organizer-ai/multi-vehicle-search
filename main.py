import json
from typing import List, Dict, Optional
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# --- Pydantic Models for Validation ---
class VehicleRequest(BaseModel):
    length: int
    quantity: int

class SearchResult(BaseModel):
    location_id: str
    listing_ids: List[str]
    total_price_in_cents: int

# --- Global In-Memory Datastore ---
# In a real app this would be a DB query, but for the take-home, 
# load it into memory on startup.
with open('listings.json', 'r') as f:
    all_listings = json.load(f)

# Group listings by location_id for O(1) lookups
locations_map = {}
for listing in all_listings:
    loc_id = listing['location_id']
    if loc_id not in locations_map:
        locations_map[loc_id] = []
    locations_map[loc_id].append(listing)


# --- Core Logic ---
def can_pack(vehicles: List[int], lanes: List[int]) -> bool:
    """
    Recursive 1D Bin Packing. 
    Checks if a list of vehicle lengths can fit into a list of lane capacities.
    """
    def backtrack(v_idx: int) -> bool:
        # Base Case: All vehicles have been successfully packed
        if v_idx == len(vehicles):
            return True
            
        v = vehicles[v_idx]
        
        for i in range(len(lanes)):
            # If the current lane has enough capacity for this vehicle
            if lanes[i] >= v:
                # Place vehicle
                lanes[i] -= v
                
                # Move to next vehicle
                if backtrack(v_idx + 1):
                    return True
                    
                # Backtrack: remove vehicle if this path didn't work
                lanes[i] += v
                
        return False

    return backtrack(0)


@app.post("/", response_model=List[SearchResult])
def multi_vehicle_search(requests: List[VehicleRequest]):
    # 1. Flatten the request into a list of individual vehicle lengths
    vehicles = []
    for req in requests:
        vehicles.extend([req.length] * req.quantity)
    
    # Sorting descending drastically speeds up bin packing
    vehicles.sort(reverse=True)
    
    results = []
    
    # 2. Evaluate every location independently
    for loc_id, listings in locations_map.items():
        # Sort listings by price so DFS naturally finds the cheapest options first
        sorted_listings = sorted(listings, key=lambda x: x['price_in_cents'])
        
        best_cost = float('inf')
        best_subset = []
        
        # 3. DFS to explore combinations of listings
        def dfs(idx: int, current_subset: List[Dict], current_cost: int):
            nonlocal best_cost, best_subset
            
            # BRANCH AND BOUND: Prune this branch if it's already too expensive
            if current_cost >= best_cost:
                return
            
            # Check if the current subset of listings can hold the vehicles
            if current_subset:
                lanes = []
                for ls in current_subset:
                    # Calculate how many 10ft lanes this listing provides
                    num_lanes = ls['width'] // 10
                    lanes.extend([ls['length']] * num_lanes)
                
                if can_pack(vehicles, lanes):
                    # We found a valid packing! Update our bests.
                    best_cost = current_cost
                    best_subset = [ls['id'] for ls in current_subset]
                    # We return early because adding more listings to this 
                    # valid subset will only increase the price unnecessarily.
                    return 
                    
            if idx == len(sorted_listings):
                return
                
            # Decision A: Include the current listing in our subset
            current_listing = sorted_listings[idx]
            current_subset.append(current_listing)
            dfs(idx + 1, current_subset, current_cost + current_listing['price_in_cents'])
            current_subset.pop() # backtrack
            
            # Decision B: Exclude the current listing from our subset
            dfs(idx + 1, current_subset, current_cost)

        # Kick off DFS for this location
        dfs(0, [], 0)
        
        # If we found a valid combination, format it and add to results
        if best_cost != float('inf'):
            results.append({
                "location_id": loc_id,
                "listing_ids": best_subset,
                "total_price_in_cents": best_cost
            })
            
    # 4. Final requirement: sort the results array by total_price_in_cents ascending
    results.sort(key=lambda x: x['total_price_in_cents'])
    
    return results
