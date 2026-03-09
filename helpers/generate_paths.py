#!/usr/bin/env python
import os
import sys
import json
import click
from typing import List

# Add the project root to sys.path to import our modules
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from tuxlayers import parse_dag_from_layers
from configuration.data import LayerPath, LayerPathSet

@click.command()
@click.option(
    '--layersdir', '-d', required=True,
    type=click.Path(exists=True),
    help='Folder that holds layer configuration.')
@click.option(
    '--target', '-t', required=True,
    help='The target layer ID to find paths for.')
@click.option(
    '--output', '-o', required=True,
    type=click.Path(),
    help='The output JSON file path.')
def generate_paths(layersdir, target, output):
    """
    Finds all unique paths from the root to a target layer and saves them to a JSON file.
    """
    # Mock Click context to use parse_dag_from_layers
    class MockCtx:
        def __init__(self, layersdir):
            self.obj = {'LAYER_SOURCE': layersdir}
    
    ctx = MockCtx(layersdir)
    print(f"Loading DAG from {layersdir}...")
    dag = parse_dag_from_layers(ctx)
    
    print(f"Finding paths to '{target}'...")
    raw_paths = dag.get_all_paths(target)
    
    if not raw_paths:
        print(f"Error: No paths found to target '{target}'.")
        sys.exit(1)
    
    path_set = LayerPathSet()
    for i, p in enumerate(raw_paths, 1):
        path_id = f"{target}-path-{i}"
        l_path = LayerPath(
            id=path_id,
            target_layer=target,
            layers=p,
            title=f"Path {i} to {target}",
            description=f"Automatically generated path through: {' -> '.join(p)}"
        )
        path_set.paths.append(l_path)
        print(f"Discovered: {' -> '.join(p)}")

    print(f"Saving {len(path_set.paths)} paths to {output}...")
    with open(output, 'w') as f:
        f.write(path_set.to_json(indent=2))
    print("Done.")

if __name__ == "__main__":
    generate_paths()
