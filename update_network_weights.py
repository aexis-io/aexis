import json
import math
import os

def calculate_distance(p1, p2):
    return math.sqrt((p1['x'] - p2['x'])**2 + (p1['y'] - p2['y'])**2)

def main():
    path = "aexis/network.json"
    with open(path, 'r') as f:
        data = json.load(f)

    # Create a lookup for node coordinates
    nodes = {n['id']: n['coordinate'] for n in data['nodes']}
    
    updated_count = 0
    
    for node in data['nodes']:
        start_coord = node['coordinate']
        if 'adj' in node:
            for adj in node['adj']:
                target_id = adj['node_id']
                if target_id in nodes:
                    end_coord = nodes[target_id]
                    dist = calculate_distance(start_coord, end_coord)
                    
                    # Weight = Geometric Distance Scaled to 100 (Assuming Dist / 100 based on context of current values 1 vs coords 300)
                    # If user meant * 100, the weight would be 30000. 1 seems to imply / 100 is closer to target.
                    # Let's use Dist / 100.
                    new_weight = round(dist / 100.0, 4)
                    
                    adj['weight'] = new_weight
                    updated_count += 1
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Updated {updated_count} edge weights in {path}")

if __name__ == "__main__":
    main()
