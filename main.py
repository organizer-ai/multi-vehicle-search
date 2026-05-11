import json
from typing import List, Dict
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
def can_pack(vehicles: List[int], subset: List[Dict]) -> bool:
    """
    Recursive 1D Bin Packing that tests both orientations for each listing.
    """
    def backtrack(v_idx: int, current_lanes: List[int], remaining_listings: List[Dict]) -> bool:
        # Base Case: All vehicles have been successfully packed
        if v_idx == len(vehicles):
            return True
            
        v = vehicles[v_idx]
        
        # 1. Try to place the vehicle in any of the currently open lanes
        for i in range(len(current_lanes)):
            if current_lanes[i] >= v:
                current_lanes[i] -= v
                # Recurse to place the next vehicle
                if backtrack(v_idx + 1, current_lanes, remaining_listings):
                    return True
                # Backtrack if this placement didn't lead to a valid solution
                current_lanes[i] += v 
                
        # 2. If it didn't fit, try opening the next available listing in our subset
        if remaining_listings:
            ls = remaining_listings[0]
            next_rem = remaining_listings[1:]
            
            # Orientation A: Drive in parallel to Length
            lanes_a = [ls['length']] * (ls['width'] // 10)
            if backtrack(v_idx, current_lanes + lanes_a, next_rem):
                return True
                
            # Orientation B: Drive in parallel to Width (Rotated 90 degrees)
            lanes_b = [ls['width']] * (ls['length'] // 10)
            if backtrack(v_idx, current_lanes + lanes_b, next_rem):
                return True
                
        return False

    return backtrack(0, [], subset)

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
                if can_pack(vehicles, current_subset):
                    # We found a valid packing! Update our bests.
                    best_cost = current_cost
                    best_subset = [ls['id'] for ls in current_subset]
                    # Return early; adding more listings only increases price
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
