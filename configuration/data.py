'''Shared data classes for patch handling'''

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

from typing import Dict
import datetime

from dataclasses import dataclass, field
from dataclasses_json import dataclass_json

@dataclass_json
@dataclass
class PatchConfig():
    """Contains one patch for a given subdir/path"""
    basePath: str
    patch: str
    tags: str = ""
    updateModulesAfterPatch: bool = False
    # This is a way to include a baseline entry into a PatchConfig to apply.
    # There might be a more "python" way to do this though...
    baseline: str = ""
    # If this is set and patch is empty, handle this as a "copy" command instead of
    # a patch command. Again: this feels wrong but I found no other way in dataclass_json to make 
    # this work nicely (e.g. /w multiple encapsulated "command-style" types instead of this)
    copyPattern: str = ""
    # Files are assumed to be located in the files subdir of config. If copySourceDir is set this is 
    # assumed to be a subdir of config/files. You can use wildcards that glob() understands. 
    # Files will be copied to a folder relative to basePath.
    copySourceDir: str = ""
    # Same here but /w script command. Scripts are expected to be located in the scripts subdir of config
    # and are assumed to run in basePath.
    script: str = ""
    # This may contain a list of files and/or glob wildcards (like resource/**/*) that gets copied with
    # the script file itself.
    scriptResources: list[str] = field(default_factory=list)

    def valid(self) -> bool:
        '''True if baseline xor patch xor script xor copy'''
        return self.is_baseline() ^ self.is_patch() ^ self.is_script() ^ self.is_copy()

    def is_script(self) -> bool:
        '''True if a script command is configured '''
        return len(self.script) > 0

    def is_copy(self) -> bool:
        '''True if a script command is configured '''
        return len(self.copyPattern) > 0

    def is_baseline(self) -> bool:
        '''True if is a baseline'''
        return len(self.baseline) > 0

    def is_patch(self) -> bool:
        '''True if a patch is defined'''
        return len(self.patch) > 0

    def has_tags(self) -> bool:
        '''True if at least one filter is defined'''
        return len(self.tags) > 0

@dataclass_json
@dataclass
class PatchSet():
    """This is used to create standalone patchsets.
    It is the result from reading a BoardConfiguration/PatchLayers and
    then written out in combination with the patches."""
    patches: list[PatchConfig] = field(default_factory=list)


@dataclass_json
@dataclass
class PatchLayer():
    """Contains a set of patches belonging together.
    Used by BoardConfiguration."""

    id: str = ""
    parent: str = ""
    title: str = ""
    description: str = "" # Used for longer documentation entries. Optional field.
    patches: list[PatchConfig] = field(default_factory=list)


@dataclass
class PatchInfo():
    '''Collects information about a patch file'''
    patchfile: str = ""
    patchfile_basename: str = ""
    joined_comment: str = ""
    comments: list[str] = field(default_factory=list)


@dataclass
class LayerInfo():
    '''Collects information about a patchlayer'''
    id: str
    title: str
    description: str

@dataclass
class Documentation():
    """ Contains all entries that can be used in a documentation template"""
    timestamp: datetime.datetime = datetime.datetime.now()
    primaryLayer: LayerInfo = LayerInfo("", "", ""),
    patches: list[PatchInfo] = field(default_factory=list)
    layers: list[LayerInfo] = field(default_factory=list)
    misc: Dict[str, str] = field(default_factory = lambda: ({}))
