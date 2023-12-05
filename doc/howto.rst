==============
Howto TuxLayers
==============

What is it?
-----------

TuxLayers is a tool to manage sets of patches for complex git repository structures containing multiple levels of submodules.
Its main features are:

- Manage, verify and apply multiple levels on dependent patchsets
- Support the used during the development of the patchsets
- Create stand-alone distributions of the patches

TuxLayers implemented using python, basing primarily on `GitPython <https://gitpython.readthedocs.io/en/stable/intro.html>`_ and `Click <https://click.palletsprojects.com/en/8.1.x/>`_ for user interaction.


Configuration
-------------

TuxLayers is based on a set of so-called layer definitions. These are json files that can depend on one another and by this form a tree. A single minimal layer file looks like this::

  {
    "id": "myself",
    "parent": "my_parent",
    "title": "An example layer without patches",
    "description": "Really, this is an empty layer. No need to complain about it."
    "patches": []
  }

Only one of the layers can have no parent and only one _must_ have no parent, providing the root node of the tree. We allow empty layers like this for grouping and/or placeholders. Usually, the patches section contains lines like these::


  "patches": [
    {
      "basePath": "submodule_a",
      "patch": "submodule_a_patches/0001-my_really_nice.patch"
    },
    {
      "basePath": "uboot-imx",
      "patch": "submodule_a_patches/0002-an_equally_nice.patch"
    }
  ]

The two entries for each patch are straightforward:

- ``basePath`` describes the submodule inside the git structure and
- ``patch`` points to the patch to apply to said submodule. The patches are executed in order they are listed.

Documentation
-------------

using the "document" command it is possible to create an automatic documentation for a given patchset. The command looks like this:

``python TuxLayers.py document --layer <layer_name> -t <jinja_template> <outpath>``

``-t <...>`` can be omitted; if this is the case a simple internal template is used.
``<outpath>`` can also be omitted; if this is the case it defaults to the current folder.

To write your own templates, please refer to the example shown in doc_templates; as for data fields, these are available:

- *data.primaryLayer*: The topmost layer selected for the build process
- *data.timestamp*: The time when documentation was created
- *data.layers*: A list of all referenced layers inside the build. In here, each element consists of:

  - *layer.id*: The short name of the layer
  - *layer.title*: If a title of the layer was provided, this can be found here.
  - *layer.description*: If a description of the layer was provided, this can be found here. This is meant to be a longer text block instead of a one-line overview as title is.

- *data.patches*: This lists all included patch files, each with a comment field (if a comment was provided):

  - *patch.patchfile*: The filename of the patch
  - *patch.comments*: A list of strings that were extracted from the comment section of the patch file (each line before the actual start of the patch beginning with ``#``)
