Create a patchset for a given layer.
====================================

Arguments:

-  ``-d``: folder containing the layer definitions. Defaults to config/layers above tuxlayers.
-  ``-p``: folder containing the patches referred in the layers. Defaults to config/patches above tuxlayers.
-  ``-l``: The layer we want to create the patchset for
-  positional arg in the end: target folder to write evertything to

``python TuxLayers.py patchset -l my_demo_layer ~/my_demo_layer_output``
 Apply a created patchset to a given repository
=======================================

Arguments:

-  ``-w``: base git folder we want to apply to
-  ``-p``: folder containing the patchset. Defaults to config/patches above ./tuxlayers
-  ``-f``: The layer to start from in the patchset. Defaults to empty
   (all layers)
-  ``-b``: Add baseline commits to the git repo structure

This example all levels of patches to the repo in ~/demo_repo/:
``python TuxLayers.py apply -w ~/demo_repo  -b``

List all baselines
==================

Arguments:

-  ``-w``: base git folder we want to work on

This example only adds the last layer of patches to the repo in
~/demo_repo/:

``python TuxLayers.py showbaselines -w ~/demo_repo/``

Revert to a baseline:
=====================

Arguments:

-  ``-w``: base git folder we want to work on
-  ``-a``: revert all baselines
-  positional arg in the end: baseline to remove (and all above it)

This example removes all baselines:
``python TuxLayers.py reverttobaseline -w ~/demo_repo/ -a``

This example removes everything after (and including) buildme_fixes:
``python TuxLayers.py reverttobaseline -w ~/demo_repo/ buildme_fixes``

Manually add a baseline:
========================

Arguments:

-  ``-w``: base git folder we want to work on
-  positional arg in the end: baseline to remove (and all above it)

This example adds my_baseline to the current head of all (sub)repos:
``python TuxLayers.py addbaseline -w ~/demo_repo/ my_baseline``
