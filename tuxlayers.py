#!/usr/bin/env python
'''tuxlayers is used to maintain a hiearchy of
patches for git repos with submodules'''

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

import glob
import logging
import os
import copy
import json
from typing import Dict, List, Set, Optional

import click
import coloredlogs
from graphlib import TopologicalSorter

from commands import baseline, info, patchset
from configuration.data import PatchLayer, LayerPathSet
from shared.helpers import exit_with_error

# Logging setup...
logger = logging.getLogger(__name__)

class Node:
    def __init__(self, identifier, data, tag=None, path_data=None):
        self.identifier = identifier
        self.data = data
        self.tag = tag if tag else identifier
        self.path_data = path_data # Stores LayerPath if this is a dummy node

class LayerDAG:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[str, Set[str]] = {} # child -> set of parents
        self.root = None

    def create_node(self, identifier, tag=None, data=None, parent=None, path_data=None):
        if identifier not in self.nodes:
            self.nodes[identifier] = Node(identifier, data, tag, path_data)
            self.edges[identifier] = set()
            if parent is None and self.root is None:
                self.root = identifier
        
        if parent:
            if parent not in self.nodes:
                raise ValueError(f"Parent {parent} does not exist")
            self.edges[identifier].add(parent)

    def get_node(self, identifier) -> Optional[Node]:
        return self.nodes.get(identifier)

    def parents(self, identifier) -> List[str]:
        return list(self.edges.get(identifier, set()))

    def leaves(self) -> List[Node]:
        all_parents = set()
        for parents in self.edges.values():
            all_parents.update(parents)
        return [node for id, node in self.nodes.items() if id not in all_parents]

    def show(self):
        print("Layer DAG Structure:")
        # Simple indentation-based print for the DAG (topological sort order)
        try:
            ts = TopologicalSorter(self.edges)
            order = list(ts.static_order())
            # For tree-like display we can use a recursive approach from root
            self._show_recursive(self.root, 0, set())
        except Exception as e:
            logger.error("Could not show DAG: %s", e)

    def _show_recursive(self, node_id, level, visited):
        if node_id is None or node_id not in self.nodes:
            return
        
        prefix = "    " * level + "└── " if level > 0 else ""
        print(f"{prefix}{node_id}")
        
        # Find children
        children = [child_id for child_id, parents in self.edges.items() if node_id in parents]
        for child in children:
            self._show_recursive(child, level + 1, visited)

    def get_all_ancestors(self, node_id) -> List[Node]:
        """Returns all ancestors of a node in topological order"""
        if node_id not in self.nodes:
            return []
        
        ancestors_ids = set()
        to_visit = [node_id]
        while to_visit:
            curr = to_visit.pop(0)
            for p in self.edges.get(curr, set()):
                if p not in ancestors_ids:
                    ancestors_ids.add(p)
                    to_visit.append(p)
        
        # Sub-graph edges for topological sort
        sub_edges = {id: self.edges[id] & ancestors_ids for id in ancestors_ids}
        sub_edges[node_id] = self.edges[node_id] & ancestors_ids
        
        try:
            ts = TopologicalSorter(sub_edges)
            return [self.nodes[id] for id in ts.static_order()]
        except Exception:
            # Fallback to simple path if topological sort fails (should not happen in DAG)
            return [self.nodes[node_id]]

    def get_all_paths(self, target_node_id) -> List[List[str]]:
        """Returns all simple paths from the root to the target node."""
        import networkx as nx
        dg = self.to_networkx()
        if self.root is None or target_node_id not in dg:
            return []
        
        # nx.all_simple_paths returns a generator of paths
        return list(nx.all_simple_paths(dg, source=self.root, target=target_node_id))

    def to_networkx(self):
        """Converts the DAG to a networkx DiGraph"""
        import networkx as nx
        dg = nx.DiGraph()
        for node_id in self.nodes:
            dg.add_node(node_id)
        for child_id, parents in self.edges.items():
            for parent_id in parents:
                dg.add_edge(parent_id, child_id)
        return dg

    def to_dot(self, output_path):
        """Exports the DAG to DOT format using networkx"""
        import networkx as nx
        from networkx.drawing.nx_pydot import write_dot
        dg = self.to_networkx()
        logger.info("Exporting graph to DOT: %s", output_path)
        write_dot(dg, output_path)

    def to_graphml(self, output_path):
        """Exports the DAG to GraphML format using networkx"""
        import networkx as nx
        dg = self.to_networkx()
        logger.info("Exporting graph to GraphML: %s", output_path)
        nx.write_graphml(dg, output_path)

@click.group(
    help='''tuxlayers is used to maintain a hiearchy
    of patches for git repositories with submodules''')
# pass configuration via the context
@click.option(
    '--layersdir', '-d', required=False,
    type=click.Path(),
    default=os.path.join(os.path.dirname(os.path.realpath(__file__)), "config", "layers"),
    help='Folder that holds layer configuration. Defaults to config/layers above the executable.')
@click.option(
    '--pathdir', '-p', required=False,
    type=click.Path(),
    default=os.path.join(os.path.dirname(os.path.realpath(__file__)), "config", "paths"),
    help='Folder that holds path configuration. Defaults to config/paths above the executable.')
@click.option(
    '--log_level', '-L', required=False, default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARN", "ERROR"],
                      case_sensitive=False),
    show_default=True,
    help='Set log level.')
@click.pass_context
def cli(ctx, log_level, layersdir, pathdir):
    """This is run before all other commands;
    used to provide context content."""
    # activate logging first...
    coloredlogs.install(level=log_level, milliseconds=True)
    logger.info("Reading layer configuration from %s", layersdir)
    # now prepare config & pass it via context
    ctx.ensure_object(dict)
    if layersdir:
        ctx.obj['LAYER_SOURCE'] = layersdir
        ctx.obj['PATHS_SOURCE'] = pathdir
        ctx.obj['LAYER_DAG'] = parse_dag_from_layers(ctx)

        leaves = ctx.obj['LAYER_DAG'].leaves()

        ctx.obj['LEAVES'] = leaves
    else:
        logger.info("No layers selected. Continuing without them.")


def parse_dag_from_layers(ctx):
    '''load all json files found in the config
    folder that contain a valid layer config'''

    previous_dir = os.path.abspath(os.getcwd())
    layers_dir = ctx.obj['LAYER_SOURCE']

    if not os.path.isdir(layers_dir):
        exit_with_error("Layers dir invalid")
    os.chdir(layers_dir)

    layer_files = glob.glob("**/*.json", recursive=True)
    ctx.obj['LAYER_FILES'] = layer_files
    layers = {}
    base_layer = None

    os.chdir(previous_dir)

    for layer_file in layer_files:
        logger.info("Loading layer configuration from: %s", layer_file)
        layer_config = load_layer_config(layers_dir, layer_file)
        layer_id = layer_config.id
        if not layer_config.have_parent():
            if base_layer is not None:
                exit_with_error(
                    '''Found duplicate base layer
                    in layer configuration: ''' + layer_file)
            base_layer = layer_config
        else:
            if layer_id in layers:
                exit_with_error(
                    "Found duplicate in layer configuration: " + layer_file)
            layers[layer_id] = layer_config

    layer_dag = LayerDAG()
    if base_layer is None:
        return layer_dag
    
    layer_dag.create_node(base_layer.id, base_layer.id, data=base_layer)
    
    new_edges = True
    while new_edges:
        new_edges = False
        # iterate through all defined layers and see if their parents are already in the DAG
        for layer_id, layer in list(layers.items()):
            # Handle single parent
            if layer.parent and layer.parent in layer_dag.nodes:
                if layer_id not in layer_dag.nodes:
                    layer_dag.create_node(layer_id, layer_id, data=layer, parent=layer.parent)
                    new_edges = True
                elif layer.parent not in layer_dag.edges[layer_id]:
                    layer_dag.edges[layer_id].add(layer.parent)
                    new_edges = True
            
            # Handle multi parents
            if layer.parents:
                for parent_id in layer.parents:
                    if parent_id in layer_dag.nodes:
                        if layer_id not in layer_dag.nodes:
                            layer_dag.create_node(layer_id, layer_id, data=layer, parent=parent_id)
                            new_edges = True
                        elif parent_id not in layer_dag.edges[layer_id]:
                            layer_dag.edges[layer_id].add(parent_id)
                            new_edges = True

    # Now parse path configuration and add dummy nodes
    paths_dir = ctx.obj.get('PATHS_SOURCE')
    if paths_dir and os.path.isdir(paths_dir):
        parse_path_configs_and_add_dummy_nodes(paths_dir, layer_dag)

    return layer_dag

def parse_path_configs_and_add_dummy_nodes(paths_dir, layer_dag):
    """Parses path configuration files and adds valid paths as dummy nodes to the DAG."""
    for root, _, files in os.walk(paths_dir):
        for file in files:
            if file.endswith(".json"):
                path_file = os.path.join(root, file)
                try:
                    with open(path_file, encoding='UTF-8') as json_content:
                        data_json = json_content.read()
                        # Check if it's a valid path set by seeing if 'paths' key exists
                        data_dict = json.loads(data_json)
                        if isinstance(data_dict, dict) and 'paths' in data_dict:
                            logger.info("Loading path configuration from: %s", path_file)
                            path_set = LayerPathSet.from_json(data_json)
                            for path in path_set.paths:
                                if validate_path(path, layer_dag):
                                    logger.info("Adding dummy node for path: %s to parent %s", path.id, path.target_layer)
                                    dummy_layer = PatchLayer(
                                        id=path.id,
                                        title=path.title,
                                        description=path.description,
                                        parent=path.target_layer,
                                        layers=path.layers
                                    )
                                    layer_dag.create_node(path.id, tag=path.id, data=dummy_layer, parent=path.target_layer)
                                else:
                                    logger.warning("Path %s is invalid for the current DAG.", path.id)
                except Exception as e:
                    # Silently skip files that aren't path configurations or fail to parse
                    pass

def validate_path(path, layer_dag):
    """Validates that a path is consistent with the DAG."""
    # Check that all layers in the path exist in the DAG
    for layer_id in path.layers:
        if layer_id not in layer_dag.nodes:
            logger.warning("Layer %s in path %s not found in DAG.", layer_id, path.id)
            return False
    
    # Check connectivity
    for i in range(len(path.layers) - 1):
        parent = path.layers[i]
        child = path.layers[i+1]
        if parent not in layer_dag.edges.get(child, set()):
            logger.warning("Connectivity broken in path %s: %s -> %s", path.id, parent, child)
            return False
            
    # Check if target_layer matches the end of the path
    if path.target_layer != path.layers[-1]:
        logger.warning("Target layer %s does not match the end of path %s (%s).", 
                       path.target_layer, path.id, path.layers[-1])
        return False
        
    return True

def load_layer_config(config_folder, layer_filename):
    """Loads layer config for a given type"""
    layer_file = os.path.abspath(os.path.join(config_folder, layer_filename))
    if not os.path.isfile(layer_file):
        exit_with_error("Could not find " + layer_file)

    with open(layer_file, encoding='UTF-8') as json_content:
        # Further file processing goes here
        data_json = json_content.read()
        try:
            # pylint: disable=no-member
            data_layer = PatchLayer.from_json(data_json)
            return data_layer
        except ValueError as value_error:
            exit_with_error(value_error)
    return PatchLayer(id='', parent='', description='', title='')


cli.add_command(info.info)
cli.add_command(patchset.patchset)
cli.add_command(patchset.apply)
cli.add_command(patchset.document)
cli.add_command(baseline.listsubmodules)
cli.add_command(baseline.addbaseline)
cli.add_command(baseline.reverttobaseline)
cli.add_command(baseline.showbaselines)
cli.add_command(baseline.createpatches)

if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    cli()
