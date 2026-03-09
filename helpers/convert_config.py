#!/usr/bin/env python3
import json
import os
import glob
import sys

def convert_layers(layers_dir):
    """
    Converts legacy TuxLayers configurations to the new DAG-based format.
    1. Maps all tree_ids to the original layer 'id'.
    2. Updates 'parent' and 'parents' references to use the actual 'id'.
    3. Removes the 'tree_ids' field from all JSON files.
    """
    id_map = {}
    layer_files = glob.glob(os.path.join(layers_dir, "**/*.json"), recursive=True)
    
    configs = {}
    # First pass: Build the tree_id -> actual_id mapping
    for f in layer_files:
        try:
            with open(f, 'r') as jf:
                data = json.load(jf)
                configs[f] = data
                layer_id = data.get('id')
                tree_ids = data.get('tree_ids', [])
                if tree_ids:
                    for tid in tree_ids:
                        if tid and tid != layer_id:
                            id_map[tid] = layer_id
                            print(f"Mapping tree_id '{tid}' -> actual_id '{layer_id}'")
        except Exception as e:
            print(f"Error reading {f}: {e}")

    # Second pass: Update references and clean up
    for f, data in configs.items():
        modified = False
        
        # Update single parent reference
        if 'parent' in data:
            old_parent = data['parent']
            if old_parent in id_map:
                data['parent'] = id_map[old_parent]
                modified = True
        
        # Update multi-parent list
        if 'parents' in data:
            old_parents = data['parents']
            new_parents = [id_map.get(p, p) for p in old_parents]
            if new_parents != old_parents:
                # Deduplicate while preserving order
                data['parents'] = list(dict.fromkeys(new_parents))
                modified = True
            
        # Remove the legacy tree_ids field
        if 'tree_ids' in data:
            del data['tree_ids']
            modified = True
            
        if modified:
            with open(f, 'w') as jf:
                json.dump(data, jf, indent=2)
            print(f"Successfully converted: {f}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 convert_config.py <path_to_layers_dir>")
        sys.exit(1)
        
    target_dir = sys.argv[1]
    if os.path.isdir(target_dir):
        convert_layers(target_dir)
    else:
        print(f"Error: {target_dir} is not a valid directory.")
