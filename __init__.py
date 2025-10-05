bl_info = {
    "name": "Helldivers 2 SDK: Community Edition",
    "version": (3, 0, 0),
    "blender": (4, 0, 0),
    "category": "Import-Export",
}

#region Imports

# System
import ctypes, os, tempfile, subprocess, time, webbrowser, shutil, datetime
import random as r
from copy import deepcopy
import copy
from math import ceil
from pathlib import Path
import configparser
import requests
import json
import struct
import concurrent.futures

#import pyautogui 

# Blender
import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import StringProperty, BoolProperty, IntProperty, EnumProperty, PointerProperty, CollectionProperty
from bpy.types import Panel, Operator, PropertyGroup, Scene, Menu, OperatorFileListElement, UIList

from .stingray.animation import StingrayAnimation, AnimationException
from .stingray.raw_dump import StingrayRawDump
from .stingray.material import LoadShaderVariables, StingrayMaterial
from .stingray.texture import StingrayTexture
from .stingray.particle import StingrayParticles
from .stingray.bones import LoadBoneHashes, StingrayBones
from .stingray.composite_unit import StingrayCompositeMesh
from .stingray.unit import CreateModel, GetObjectsMeshData, StingrayMeshFile

from .hashlists.hash import murmur64_hash

# Local
# NOTE: Not bothering to do importlib reloading shit because these modules are unlikely to be modified frequently enough to warrant testing without Blender restarts
from .memoryStream import MemoryStream
from .logger import PrettyPrint

from .constants import *

#endregion

#region Global Variables

AddonPath = os.path.dirname(__file__)

Global_texconvpath       = f"{AddonPath}\\deps\\texconv.exe"
Global_materialpath      = f"{AddonPath}\\materials"
Global_typehashpath      = f"{AddonPath}\\hashlists\\typehash.txt"
Global_filehashpath      = f"{AddonPath}\\hashlists\\filehash.txt"
Global_friendlynamespath = f"{AddonPath}\\hashlists\\friendlynames.txt"

Global_archivehashpath   = f"{AddonPath}\\hashlists\\archivehashes.json"
Global_variablespath     = f"{AddonPath}\\hashlists\\shadervariables.txt"
Global_bonehashpath      = f"{AddonPath}\\hashlists\\bonehash.txt"

Global_defaultgamepath   = "C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\data\ "
Global_defaultgamepath   = Global_defaultgamepath[:len(Global_defaultgamepath) - 1]
Global_gamepath          = ""
Global_gamepathIsValid   = False
Global_searchpath        = ""
Global_configpath        = f"{AddonPath}.ini"
Global_backslash         = "\-".replace("-", "")

Global_Foldouts = []

Global_BoneNames = {}

Global_SectionHeader = "---------- Helldivers 2 ----------"

Global_randomID = ""

Global_latestVersionLink = "https://api.github.com/repos/Boxofbiscuits97/HD2SDK-CommunityEdition/releases/latest"
Global_addonUpToDate = None

Global_archieHashLink = "https://raw.githubusercontent.com/Boxofbiscuits97/HD2SDK-CommunityEdition/main/hashlists/archivehashes.json"

Global_previousRandomHash = 0

#endregion

#region Common Hashes & Lookups

TextureTypeLookup = {
    "original": (
        "PBR", 
        "", 
        "", 
        "", 
        "Bump Map", 
        "Normal", 
        "", 
        "Emission", 
        "Bump Map", 
        "Base Color", 
        "", 
        "", 
        ""
    ),
    "basic": (
        "PBR", 
        "Base Color", 
        "Normal"
    ),
    "basic+": (
        "PBR",
        "Base Color",
        "Normal"
    ),
    "emissive": (
        "Normal/AO/Roughness", 
        "Emission", 
        "Base Color/Metallic"
    ),
        "armorlut": (
        "Decal", 
        "", 
        "Pattern LUT", 
        "Normal", 
        "", 
        "", 
        "Pattern Mask", 
        "ID Mask Array", 
        "", 
        "Primary LUT", 
        "",
    ),
    "alphaclip": (
        "Normal/AO/Roughness",
        "Alpha Mask",
        "Base Color/Metallic"
    ),
    "advanced": (
        "",
        "",
        "Normal/AO/Roughness",
        "Metallic",
        "",
        "Color/Emission Mask",
        "",
        "",
        "",
        "",
        ""
    ),
    "translucent": (
        "Normal",
    )
}

Global_Materials = (
        ("advanced", "Advanced", "A more comlpicated material, that is color, normal, emission and PBR capable which renders in the UI. Sourced from the Illuminate Overseer."),
        ("basic+", "Basic+", "A basic material with a color, normal, and PBR map which renders in the UI, Sourced from a SEAF NPC"),
        ("translucent", "Translucent", "A translucent with a solid set color and normal map. Sourced from the Terminid Larva Backpack."),
        ("alphaclip", "Alpha Clip", "A material that supports an alpha mask which does not render in the UI. Sourced from a skeleton pile"),
        ("original", "Original", "The original template used for all mods uploaded to Nexus prior to the addon's public release, which is bloated with additional unnecessary textures. Sourced from a terminid"),
        ("basic", "Basic", "A basic material with a color, normal, and PBR map. Sourced from a trash bag prop"),
        ("emissive", "Emissive", "A basic material with a color, normal, and emission map. Sourced from a vending machine"),
        ("armorlut", "Armor LUT", "An advanced material using multiple mask textures and LUTs to texture the mesh only advanced users should be using this. Sourced from the base game material on Armors"),
    )

#endregion

#region Functions: Miscellaneous

# 4.3 compatibility change
def CheckBlenderVersion():
    global OnCorrectBlenderVersion
    BlenderVersion = bpy.app.version
    OnCorrectBlenderVersion = (BlenderVersion[0] == 4 and BlenderVersion[1] <= 3)
    PrettyPrint(f"Blender Version: {BlenderVersion} Correct Version: {OnCorrectBlenderVersion}")

def CheckAddonUpToDate():
    PrettyPrint("Checking If Addon is up to date...")
    currentVersion = bl_info["version"]
    try:
        req = requests.get(Global_latestVersionLink, timeout=5)
        req.raise_for_status()  # Check if the request is successful.
        if req.status_code == requests.codes.ok:
            req = req.json()
            latestVersion = req['tag_name'].replace("v", "").replace("-", ".").split(".")
            latestVersion = (int(latestVersion[0]), int(latestVersion[1]), int(latestVersion[2]))
            
            PrettyPrint(f"Current Version: {currentVersion}")
            PrettyPrint(f"Latest Version: {latestVersion}")

            global Global_addonUpToDate
            global Global_latestAddonVersion
            Global_addonUpToDate = latestVersion == currentVersion
            Global_latestAddonVersion = f"{latestVersion[0]}.{latestVersion[1]}.{latestVersion[2]}"

            if Global_addonUpToDate:
                PrettyPrint("Addon is up to date!")
            else:
                PrettyPrint("Addon is outdated!")
        else:
            PrettyPrint(f"Request Failed, Cannot check latest Version. Status: {req.status_code}", "warn")
    except requests.ConnectionError:
        PrettyPrint("Connection failed. Please check your network settings.", "warn")
    except requests.HTTPError as err:
        PrettyPrint(f"HTTP error occurred: {err}", "warn")
        
def UpdateArchiveHashes():
    try:
        req = requests.get(Global_archieHashLink)
        req.raise_for_status()  # Check if the request is successful.
        if req.status_code == requests.codes.ok:
            file = open(Global_archivehashpath, "w")
            file.write(req.text)
            PrettyPrint(f"Updated Archive Hashes File")
        else:
            PrettyPrint(f"Request Failed, Could not update Archive Hashes File", "warn")
    except requests.ConnectionError:
        PrettyPrint("Connection failed. Please check your network settings.", "warn")
    except requests.HTTPError as err:
        PrettyPrint(f"HTTP error occurred: {err}", "warn")

def EntriesFromStrings(file_id_string, type_id_string):
    FileIDs = file_id_string.split(',')
    TypeIDs = type_id_string.split(',')
    Entries = []
    for n in range(len(FileIDs)):
        if FileIDs[n] != "":
            Entries.append(Global_TocManager.GetEntry(int(FileIDs[n]), int(TypeIDs[n])))
    return Entries

def EntriesFromString(file_id_string, TypeID):
    FileIDs = file_id_string.split(',')
    Entries = []
    for n in range(len(FileIDs)):
        if FileIDs[n] != "":
            Entries.append(Global_TocManager.GetEntry(int(FileIDs[n]), int(TypeID)))
    return Entries

def IDsFromString(file_id_string):
    FileIDs = file_id_string.split(',')
    Entries = []
    for n in range(len(FileIDs)):
        if FileIDs[n] != "":
            Entries.append(int(FileIDs[n]))
    return Entries

def GetDisplayData():
    # Set display archive TODO: Global_TocManager.LastSelected Draw Index could be wrong if we switch to patch only mode, that should be fixed
    DisplayTocEntries = []
    DisplayTocTypes   = []
    DisplayArchive = Global_TocManager.ActiveArchive
    if bpy.context.scene.Hd2ToolPanelSettings.PatchOnly:
        if Global_TocManager.ActivePatch != None:
            DisplayTocEntries = [[Entry, True] for Entry in Global_TocManager.ActivePatch.TocEntries]
            DisplayTocTypes   = Global_TocManager.ActivePatch.TocTypes
    elif Global_TocManager.ActiveArchive != None:
        DisplayTocEntries = [[Entry, False] for Entry in Global_TocManager.ActiveArchive.TocEntries]
        DisplayTocTypes   = [Type for Type in Global_TocManager.ActiveArchive.TocTypes]
        AddedTypes   = [Type.TypeID for Type in DisplayTocTypes]
        AddedEntries = [Entry[0].FileID for Entry in DisplayTocEntries]
        if Global_TocManager.ActivePatch != None:
            for Type in Global_TocManager.ActivePatch.TocTypes:
                if Type.TypeID not in AddedTypes:
                    AddedTypes.append(Type.TypeID)
                    DisplayTocTypes.append(Type)
            for Entry in Global_TocManager.ActivePatch.TocEntries:
                if Entry.FileID not in AddedEntries:
                    AddedEntries.append(Entry.FileID)
                    DisplayTocEntries.append([Entry, True])
    return [DisplayTocEntries, DisplayTocTypes]

def SaveUnsavedEntries(self):
    for Entry in Global_TocManager.ActivePatch.TocEntries:
                if not Entry.IsModified:
                    Global_TocManager.Save(int(Entry.FileID), Entry.TypeID)
                    PrettyPrint(f"Saved {int(Entry.FileID)}")

def RandomHash16():
    global Global_previousRandomHash
    hash = Global_previousRandomHash
    while hash == Global_previousRandomHash:
        r.seed(datetime.datetime.now().timestamp())
        hash = r.randint(1, 0xffffffffffffffff)
    Global_previousRandomHash = hash
    PrettyPrint(f"Generated hash: {hash}")
    return hash
#endregion

#region Functions: Stingray Hashing

def GetTypeNameFromID(ID):
    for hash_info in Global_TypeHashes:
        if int(ID) == hash_info[0]:
            return hash_info[1]
    return "unknown"

def GetIDFromTypeName(Name):
    for hash_info in Global_TypeHashes:
        if hash_info[1] == Name:
            return int(hash_info[0])
    return None

def GetFriendlyNameFromID(ID):
    for hash_info in Global_NameHashes:
        if int(ID) == hash_info[0]:
            if hash_info[1] != "":
                return hash_info[1]
    return str(ID)

def GetArchiveNameFromID(EntryID):
    for hash in Global_ArchiveHashes:
        if hash[0] == EntryID:
            return hash[1]
    return ""

def GetArchiveIDFromName(Name):
    for hash in Global_ArchiveHashes:
        if hash[1] == Name:
            return hash[0]
    return ""

def HasFriendlyName(ID):
    for hash_info in Global_NameHashes:
        if int(ID) == hash_info[0]:
            return True
    return False

def AddFriendlyName(ID, Name):
    Global_TocManager.SavedFriendlyNames = []
    Global_TocManager.SavedFriendlyNameIDs = []
    for hash_info in Global_NameHashes:
        if int(ID) == hash_info[0]:
            hash_info[1] = str(Name)
            return
    Global_NameHashes.append([int(ID), str(Name)])
    SaveFriendlyNames()

def SaveFriendlyNames():
    with open(Global_filehashpath, 'w') as f:
        for hash_info in Global_NameHashes:
            if hash_info[1] != "" and int(hash_info[0]) == murmur64_hash(hash_info[1].encode()):
                string = str(hash_info[0]) + " " + str(hash_info[1])
                f.writelines(string+"\n")
    with open(Global_friendlynamespath, 'w') as f:
        for hash_info in Global_NameHashes:
            if hash_info[1] != "":
                string = str(hash_info[0]) + " " + str(hash_info[1])
                f.writelines(string+"\n")

#endregion

#region Functions: Initialization

Global_TypeHashes = []
def LoadTypeHashes():
    with open(Global_typehashpath, 'r') as f:
        for line in f.readlines():
            parts = line.split(" ")
            Global_TypeHashes.append([int(parts[0], 16), parts[1].replace("\n", "")])

Global_NameHashes = []
def LoadNameHashes():
    Loaded = []
    with open(Global_filehashpath, 'r') as f:
        for line in f.readlines():
            parts = line.split(" ")
            Global_NameHashes.append([int(parts[0]), parts[1].replace("\n", "")])
            Loaded.append(int(parts[0]))
    with open(Global_friendlynamespath, 'r') as f:
        for line in f.readlines():
            parts = line.split(" ", 1)
            if int(parts[0]) not in Loaded:
                Global_NameHashes.append([int(parts[0]), parts[1].replace("\n", "")])
                Loaded.append(int(parts[0]))

Global_ArchiveHashes = []
def LoadHash(path, title):
    with open(path, 'r') as f:
        for line in f.readlines():
            parts = line.split(" ", 1)
            Global_ArchiveHashes.append([parts[0], title + parts[1].replace("\n", "")])
                
def LoadArchiveHashes():
    file = open(Global_archivehashpath, "r")
    data = json.load(file)

    for title in data:
        for innerKey in data[title]:
            Global_ArchiveHashes.append([innerKey, title + ": " + data[title][innerKey]])

    Global_ArchiveHashes.append([BaseArchiveHexID, "SDK: Base Patch Archive"])

def GetEntryParentMaterialID(entry):
    if entry.TypeID == MaterialID:
        f = MemoryStream(entry.TocData)
        for i in range(6):
            f.uint32(0)
        parentID = f.uint64(0)
        return parentID
    else:
        raise Exception(f"Entry: {entry.FileID} is not a material")

#endregion

#region Configuration

def InitializeConfig():
    global Global_gamepath, Global_searchpath, Global_configpath, Global_gamepathIsValid
    if os.path.exists(Global_configpath):
        config = configparser.ConfigParser()
        config.read(Global_configpath, encoding='utf-8')
        try:
            Global_gamepath = config['DEFAULT']['filepath']
            Global_searchpath = config['DEFAULT']['searchpath']
        except:
            UpdateConfig()
        if os.path.exists(Global_gamepath):
            PrettyPrint(f"Loaded Data Folder: {Global_gamepath}")
            Global_gamepathIsValid = True
        else:
            PrettyPrint(f"Game path: {Global_gamepath} is not a valid directory", 'ERROR')
            Global_gamepathIsValid = False

    else:
        UpdateConfig()

def UpdateConfig():
    global Global_gamepath, Global_searchpath, Global_defaultgamepath
    if Global_gamepath == "":
        Global_gamepath = Global_defaultgamepath
    config = configparser.ConfigParser()
    config['DEFAULT'] = {'filepath' : Global_gamepath, 'searchpath' : Global_searchpath}
    with open(Global_configpath, 'w') as configfile:
        config.write(configfile)
    
#endregion

#region Classes and Functions: Stingray Archives

class TocEntry:

    def __init__(self):
        self.FileID = self.TypeID = self.TocDataOffset = self.Unknown1 = self.GpuResourceOffset = self.Unknown2 = self.TocDataSize = self.GpuResourceSize = self.EntryIndex = self.StreamSize = self.StreamOffset = 0
        self.Unknown3 = 16
        self.Unknown4 = 64

        self.TocData =  self.TocData_OLD = b""
        self.GpuData =  self.GpuData_OLD = b""
        self.StreamData =  self.StreamData_OLD = b""

        # Custom Dev stuff
        self.LoadedData = None
        self.IsLoaded   = False
        self.IsModified = False
        self.IsCreated  = False # custom created, can be removed from archive
        self.IsSelected = False
        self.MaterialTemplate = None # for determining tuple to use for labeling textures in the material editor
        self.DEV_DrawIndex = -1

    # -- Serialize TocEntry -- #
    def Serialize(self, TocFile: MemoryStream, Index=0):
        self.FileID             = TocFile.uint64(self.FileID)
        self.TypeID             = TocFile.uint64(self.TypeID)
        self.TocDataOffset      = TocFile.uint64(self.TocDataOffset)
        self.StreamOffset       = TocFile.uint64(self.StreamOffset)
        self.GpuResourceOffset  = TocFile.uint64(self.GpuResourceOffset)
        self.Unknown1           = TocFile.uint64(self.Unknown1)
        self.Unknown2           = TocFile.uint64(self.Unknown2)
        self.TocDataSize        = TocFile.uint32(len(self.TocData))
        self.StreamSize         = TocFile.uint32(len(self.StreamData))
        self.GpuResourceSize    = TocFile.uint32(len(self.GpuData))
        self.Unknown3           = TocFile.uint32(self.Unknown3)
        self.Unknown4           = TocFile.uint32(self.Unknown4)
        self.EntryIndex         = TocFile.uint32(Index)
        return self

    # -- Write TocEntry Data -- #
    def SerializeData(self, TocFile: MemoryStream, GpuFile, StreamFile):
        if TocFile.IsReading():
            TocFile.seek(self.TocDataOffset)
            self.TocData = bytearray(self.TocDataSize)
        elif TocFile.IsWriting():
            self.TocDataOffset = TocFile.tell()
        self.TocData = TocFile.bytes(self.TocData)

        if GpuFile.IsWriting(): self.GpuResourceOffset = ceil(float(GpuFile.tell())/64)*64
        if self.GpuResourceSize > 0:
            GpuFile.seek(self.GpuResourceOffset)
            if GpuFile.IsReading(): self.GpuData = bytearray(self.GpuResourceSize)
            self.GpuData = GpuFile.bytes(self.GpuData)

        if StreamFile.IsWriting(): self.StreamOffset = ceil(float(StreamFile.tell())/64)*64
        if self.StreamSize > 0:
            StreamFile.seek(self.StreamOffset)
            if StreamFile.IsReading(): self.StreamData = bytearray(self.StreamSize)
            self.StreamData = StreamFile.bytes(self.StreamData)
        if GpuFile.IsReading():
            self.TocData_OLD    = bytearray(self.TocData)
            self.GpuData_OLD    = bytearray(self.GpuData)
            self.StreamData_OLD = bytearray(self.StreamData)

    # -- Get Data -- #
    def GetData(self):
        return [self.TocData, self.GpuData, self.StreamData]
    # -- Set Data -- #
    def SetData(self, TocData, GpuData, StreamData, IsModified=True):
        self.TocData = TocData
        self.GpuData = GpuData
        self.StreamData = StreamData
        self.TocDataSize     = len(self.TocData)
        self.GpuResourceSize = len(self.GpuData)
        self.StreamSize      = len(self.StreamData)
        self.IsModified = IsModified
    # -- Undo Modified Data -- #
    def UndoModifiedData(self):
        self.TocData = bytearray(self.TocData_OLD)
        self.GpuData = bytearray(self.GpuData_OLD)
        self.StreamData = bytearray(self.StreamData_OLD)
        self.TocDataSize     = len(self.TocData)
        self.GpuResourceSize = len(self.GpuData)
        self.StreamSize      = len(self.StreamData)
        self.IsModified = False
        if self.IsLoaded:
            self.Load(True, False)
    # -- Load Data -- #
    def Load(self, Reload=False, MakeBlendObject=True, LoadMaterialSlotNames=False):
        callback = None
        if self.TypeID == MeshID: callback = LoadStingrayMesh
        if self.TypeID == TexID: callback = LoadStingrayTexture
        if self.TypeID == MaterialID: callback = LoadStingrayMaterial
        if self.TypeID == ParticleID: callback = LoadStingrayParticle
        if self.TypeID == CompositeMeshID: callback = LoadStingrayCompositeMesh
        if self.TypeID == BoneID: callback = LoadStingrayBones
        if self.TypeID == AnimationID: callback = LoadStingrayAnimation
        if callback == None: callback = LoadStingrayDump

        if callback != None:
            if self.TypeID == MeshID:
                self.LoadedData = callback(self.FileID, self.TocData, self.GpuData, self.StreamData, Reload, MakeBlendObject, LoadMaterialSlotNames)
            else:
                self.LoadedData = callback(self.FileID, self.TocData, self.GpuData, self.StreamData, Reload, MakeBlendObject)
            if self.LoadedData == None: raise Exception("Archive Entry Load Failed")
            self.IsLoaded = True

    # -- Write Data -- #
    def Save(self, **kwargs):
        if not self.IsLoaded: self.Load(True, False)
        if self.TypeID == MeshID: callback = SaveStingrayMesh
        if self.TypeID == TexID: callback = SaveStingrayTexture
        if self.TypeID == MaterialID: callback = SaveStingrayMaterial
        if self.TypeID == ParticleID: callback = SaveStingrayParticle
        if self.TypeID == AnimationID: callback = SaveStingrayAnimation
        if callback == None: callback = SaveStingrayDump

        if self.IsLoaded:
            if self.TypeID == MeshID:
                BlenderOpts = kwargs.get("BlenderOpts")
                data = callback(self, self.FileID, self.TocData, self.GpuData, self.StreamData, self.LoadedData, BlenderOpts)
            else:
                data = callback(self, self.FileID, self.TocData, self.GpuData, self.StreamData, self.LoadedData)
            self.SetData(data[0], data[1], data[2])
        return True

class TocFileType:
    def __init__(self, ID=0, NumFiles=0):
        self.unk1     = 0
        self.TypeID   = ID
        self.NumFiles = NumFiles
        self.unk2     = 16
        self.unk3     = 64
    def Serialize(self, TocFile: MemoryStream):
        self.unk1     = TocFile.uint64(self.unk1)
        self.TypeID   = TocFile.uint64(self.TypeID)
        self.NumFiles = TocFile.uint64(self.NumFiles)
        self.unk2     = TocFile.uint32(self.unk2)
        self.unk3     = TocFile.uint32(self.unk3)
        return self


class SearchToc:
    def __init__(self):
        self.TocEntries = {}
        self.fileIDs = []
        self.Path = ""
        self.Name = ""

    def HasEntry(self, file_id, type_id):
        file_id = int(file_id)
        type_id = int(type_id)
        try:
            return file_id in self.TocEntries[type_id]
        except KeyError:
            return False

    def FromFile(self, path):
        self.UpdatePath(path)
        bin_data = b""
        file = open(path, 'r+b')
        bin_data = file.read(12)
        magic, numTypes, numFiles = struct.unpack("<III", bin_data)
        if magic != 4026531857:
            file.close()
            return False

        offset = 60 + (numTypes << 5)
        bin_data = file.read(offset + 80 * numFiles)
        file.close()
        for _ in range(numFiles):
            file_id, type_id = struct.unpack_from("<QQ", bin_data, offset=offset)
            self.fileIDs.append(int(file_id))
            try:
                self.TocEntries[type_id].append(file_id)
            except KeyError:
                self.TocEntries[type_id] = [file_id]
            offset += 80
        return True

    def UpdatePath(self, path):
        self.Path = path
        self.Name = Path(path).name

class StreamToc:
    def __init__(self):
        self.magic      = self.numTypes = self.numFiles = self.unknown = 0
        self.unk4Data   = bytearray(56)
        self.TocTypes   = []
        self.TocEntries = []
        self.Path = ""
        self.Name = ""
        self.LocalName = ""

    def Serialize(self, SerializeData=True):
        # Create Toc Types Structs
        if self.TocFile.IsWriting():
            self.UpdateTypes()
        # Begin Serializing file
        self.magic      = self.TocFile.uint32(self.magic)
        if self.magic != 4026531857: return False

        self.numTypes   = self.TocFile.uint32(len(self.TocTypes))
        self.numFiles   = self.TocFile.uint32(len(self.TocEntries))
        self.unknown    = self.TocFile.uint32(self.unknown)
        self.unk4Data   = self.TocFile.bytes(self.unk4Data, 56)

        if self.TocFile.IsReading():
            self.TocTypes   = [TocFileType() for n in range(self.numTypes)]
            self.TocEntries = [TocEntry() for n in range(self.numFiles)]
        # serialize Entries in correct order
        self.TocTypes   = [Entry.Serialize(self.TocFile) for Entry in self.TocTypes]
        TocEntryStart   = self.TocFile.tell()
        if self.TocFile.IsReading(): self.TocEntries = [Entry.Serialize(self.TocFile) for Entry in self.TocEntries]
        else:
            Index = 1
            for Type in self.TocTypes:
                for Entry in self.TocEntries:
                    if Entry.TypeID == Type.TypeID:
                        Entry.Serialize(self.TocFile, Index)
                        Index += 1

        # Serialize Data
        if SerializeData:
            for FileEntry in self.TocEntries:
                FileEntry.SerializeData(self.TocFile, self.GpuFile, self.StreamFile)

        # re-write toc entry info with updated offsets
        if self.TocFile.IsWriting():
            self.TocFile.seek(TocEntryStart)
            Index = 1
            for Type in self.TocTypes:
                for Entry in self.TocEntries:
                    if Entry.TypeID == Type.TypeID:
                        Entry.Serialize(self.TocFile, Index)
                        Index += 1
        return True

    def UpdateTypes(self):
        self.TocTypes = []
        for Entry in self.TocEntries:
            exists = False
            for Type in self.TocTypes:
                if Type.TypeID == Entry.TypeID:
                    Type.NumFiles += 1; exists = True
                    break
            if not exists:
                self.TocTypes.append(TocFileType(Entry.TypeID, 1))

    def UpdatePath(self, path):
        self.Path = path
        self.Name = Path(path).name

    def FromFile(self, path, SerializeData=True):
        self.UpdatePath(path)
        with open(path, 'r+b') as f:
            self.TocFile = MemoryStream(f.read())

        self.GpuFile    = MemoryStream()
        self.StreamFile = MemoryStream()
        if SerializeData:
            if os.path.isfile(path+".gpu_resources"):
                with open(path+".gpu_resources", 'r+b') as f:
                    self.GpuFile = MemoryStream(f.read())
            if os.path.isfile(path+".stream"):
                with open(path+".stream", 'r+b') as f:
                    self.StreamFile = MemoryStream(f.read())
        return self.Serialize(SerializeData)

    def ToFile(self, path=None):
        self.TocFile = MemoryStream(IOMode = "write")
        self.GpuFile = MemoryStream(IOMode = "write")
        self.StreamFile = MemoryStream(IOMode = "write")
        self.Serialize()
        if path == None: path = self.Path

        with open(path, 'w+b') as f:
            f.write(bytes(self.TocFile.Data))
        with open(path+".gpu_resources", 'w+b') as f:
            f.write(bytes(self.GpuFile.Data))
        with open(path+".stream", 'w+b') as f:
            f.write(bytes(self.StreamFile.Data))

    def GetFileData(self, FileID, TypeID):
        for FileEntry in self.TocEntries:
            if FileEntry.FileID == FileID and FileEntry.TypeID == TypeID:
                return FileEntry.GetData()
        return None
    def GetEntry(self, FileID, TypeID):
        for Entry in self.TocEntries:
            if Entry.FileID == int(FileID) and Entry.TypeID == TypeID:
                return Entry
        return None
    def AddEntry(self, NewEntry):
        if self.GetEntry(NewEntry.FileID, NewEntry.TypeID) != None:
            raise Exception("Entry with same ID already exists")
        self.TocEntries.append(NewEntry)
        self.UpdateTypes()
    def RemoveEntry(self, FileID, TypeID):
        Entry = self.GetEntry(FileID, TypeID)
        if Entry != None:
            self.TocEntries.remove(Entry)
            self.UpdateTypes()

class TocManager():
    def __init__(self):
        self.SearchArchives  = []
        self.LoadedArchives  = []
        self.ActiveArchive   = None
        self.Patches         = []
        self.ActivePatch     = None

        self.CopyBuffer      = []
        self.SelectedEntries = []
        self.DrawChain       = []
        self.LastSelected = None # Last Entry Manually Selected
        self.SavedFriendlyNames   = []
        self.SavedFriendlyNameIDs = []
    #________________________________#
    # ---- Entry Selection Code ---- #
    def SelectEntries(self, Entries, Append=False):
        if not Append: self.DeselectAll()
        if len(Entries) == 1:
            Global_TocManager.LastSelected = Entries[0]

        for Entry in Entries:
            if Entry not in self.SelectedEntries:
                Entry.IsSelected = True
                self.SelectedEntries.append(Entry)
    def DeselectEntries(self, Entries):
        for Entry in Entries:
            Entry.IsSelected = False
            if Entry in self.SelectedEntries:
                self.SelectedEntries.remove(Entry)
    def DeselectAll(self):
        for Entry in self.SelectedEntries:
            Entry.IsSelected = False
        self.SelectedEntries = []
        self.LastSelected = None

    #________________________#
    # ---- Archive Code ---- #
    def LoadArchive(self, path, SetActive=True, IsPatch=False):
        # TODO: Add error if IsPatch is true but the path is not to a patch

        for Archive in self.LoadedArchives:
            if Archive.Path == path:
                return Archive
        archiveID = path.replace(Global_gamepath, '')
        archiveName = GetArchiveNameFromID(archiveID)
        PrettyPrint(f"Loading Archive: {archiveID} {archiveName}")
        toc = StreamToc()
        toc.FromFile(path)
        if SetActive and not IsPatch:
            unloadEmpty = bpy.context.scene.Hd2ToolPanelSettings.UnloadEmptyArchives and bpy.context.scene.Hd2ToolPanelSettings.EnableTools
            if unloadEmpty:
                if self.ArchiveNotEmpty(toc):
                    self.LoadedArchives.append(toc)
                    self.SetActive(toc)
                else:
                    PrettyPrint(f"Unloading {archiveID} as it is Empty")
            else:
                self.LoadedArchives.append(toc)
                self.SetActive(toc)
                bpy.context.scene.Hd2ToolPanelSettings.LoadedArchives = archiveID
        elif SetActive and IsPatch:
            self.Patches.append(toc)
            self.SetActivePatch(toc)

            for entry in self.ActivePatch.TocEntries:
                if entry.TypeID == MaterialID:
                    ID = GetEntryParentMaterialID(entry)
                    if ID in Global_MaterialParentIDs:
                        entry.MaterialTemplate = Global_MaterialParentIDs[ID]
                        entry.Load()
                        PrettyPrint(f"Creating Material: {entry.FileID} Template: {entry.MaterialTemplate}")
                    else:
                        PrettyPrint(f"Material: {entry.FileID} Parent ID: {ID} is not an custom material, skipping.")
        else:
            self.LoadedArchives.append(toc)

        # Get search archives
        if len(self.SearchArchives) == 0:
            futures = []
            tocs = []
            executor = concurrent.futures.ThreadPoolExecutor()
            for root, dirs, files in os.walk(Path(path).parent):
                for name in files:
                    if Path(name).suffix == "":
                        search_toc = SearchToc()
                        tocs.append(search_toc)
                        futures.append(executor.submit(search_toc.FromFile, os.path.join(root, name)))
            for index, future in enumerate(futures):
                if future.result():
                    self.SearchArchives.append(tocs[index])
            executor.shutdown()

        return toc
    
    def GetEntryByLoadArchive(self, FileID: int, TypeID: int):
        return self.GetEntry(FileID, TypeID, SearchAll=True, IgnorePatch=True)
    
    def ArchiveNotEmpty(self, toc):
        hasMaterials = False
        hasTextures = False
        hasMeshes = False
        for Entry in toc.TocEntries:
            type = Entry.TypeID
            if type == MaterialID:
                hasMaterials = True
            elif type == MeshID:
                hasMeshes = True
            elif type == TexID:
                hasTextures = True
            elif type == CompositeMeshID:
                hasMeshes = True
        return hasMaterials or hasTextures or hasMeshes

    def UnloadArchives(self):
        # TODO: Make sure all data gets unloaded...
        # some how memory can still be too high after calling this
        self.LoadedArchives = []
        self.ActiveArchive  = None
        self.SearchArchives = []
    
    def UnloadPatches(self):
        self.Patches = []
        self.SetActivePatch(None)

    def BulkLoad(self, list):
        if bpy.context.scene.Hd2ToolPanelSettings.UnloadPatches:
            self.UnloadArchives()
        for itemPath in list:
            Global_TocManager.LoadArchive(itemPath)

    def SetActive(self, Archive):
        if Archive != self.ActiveArchive:
            self.ActiveArchive = Archive
            LoadEntryLists()
            self.DeselectAll()

    def SetActiveByName(self, Name):
        for Archive in self.LoadedArchives:
            if Archive.Name == Name:
                self.SetActive(Archive)

    #______________________#
    # ---- Entry Code ---- #
    def GetEntry(self, FileID, TypeID, SearchAll=False, IgnorePatch=False):
        # Check Active Patch
        if not IgnorePatch and self.ActivePatch != None:
            Entry = self.ActivePatch.GetEntry(FileID, TypeID)
            if Entry != None:
                return Entry
        # Check Active Archive
        if self.ActiveArchive != None:
            Entry = self.ActiveArchive.GetEntry(FileID, TypeID)
            if Entry != None:
                return Entry
        # Check All Loaded Archives
        for Archive in self.LoadedArchives:
            Entry = Archive.GetEntry(FileID, TypeID)
            if Entry != None:
                return Entry
        # Check All Search Archives
        if SearchAll:
            for Archive in self.SearchArchives:
                if Archive.HasEntry(FileID, TypeID):
                    return self.LoadArchive(Archive.Path, False).GetEntry(FileID, TypeID)
            PrettyPrint(f"Could not find entry of FileID: {FileID} TypeID: {TypeID}")
        return None

    def Load(self, FileID, TypeID, Reload=False, SearchAll=False):
        Entry = self.GetEntry(FileID, TypeID, SearchAll)
        if Entry != None: Entry.Load(Reload)

    def Save(self, FileID, TypeID):
        Entry = self.GetEntry(FileID, TypeID)
        if Entry == None:
            PrettyPrint(f"Failed to save entry {FileID}")
            return False
        if not Global_TocManager.IsInPatch(Entry):
            Entry = self.AddEntryToPatch(FileID, TypeID)
        Entry.Save()
        return True

    def CopyPaste(self, Entry, GenID = False, NewID = None):
        if self.ActivePatch == None:
            raise Exception("No patch exists, please create one first")
        if self.ActivePatch:
            dup = deepcopy(Entry)
            dup.IsCreated = True
            # if self.ActivePatch.GetEntry(dup.FileID, dup.TypeID) != None and NewID == None:
            #     GenID = True
            if GenID and NewID == None: dup.FileID = RandomHash16()
            if NewID != None:
                dup.FileID = NewID

            self.ActivePatch.AddEntry(dup)
    def Copy(self, Entries):
        self.CopyBuffer = []
        for Entry in Entries:
            if Entry != None: self.CopyBuffer.append(Entry)
    def Paste(self, GenID = False, NewID = None):
        if self.ActivePatch == None:
            raise Exception("No patch exists, please create one first")
        if self.ActivePatch:
            for ToCopy in self.CopyBuffer:
                self.CopyPaste(ToCopy, GenID, NewID)
            self.CopyBuffer = []

    def ClearClipboard(self):
        self.CopyBuffer = []

    #______________________#
    # ---- Patch Code ---- #
    def PatchActiveArchive(self):
        self.ActivePatch.ToFile()

    def CreatePatchFromActive(self, name="New Patch"):
        if self.ActiveArchive == None:
            raise Exception("No Archive exists to create patch from, please open one first")

        patch = deepcopy(self.ActiveArchive)
        patch.TocEntries  = []
        patch.TocTypes    = []
        # TODO: ask for which patch index
        path = self.ActiveArchive.Path
        if path.find(".patch_") != -1:
            num = int(path[path.find(".patch_")+len(".patch_"):]) + 1
            path = path[:path.find(".patch_")] + ".patch_" + str(num)
        else:
            path += ".patch_0"
        patch.UpdatePath(path)
        patch.LocalName = name
        PrettyPrint(f"Creating Patch: {path}")
        self.Patches.append(patch)
        self.SetActivePatch(patch)

    def SetActivePatch(self, Patch):
        self.ActivePatch = Patch
        LoadEntryLists()

    def SetActivePatchByName(self, Name):
        for Patch in self.Patches:
            if Patch.Name == Name:
                self.SetActivePatch(Patch)

    def AddNewEntryToPatch(self, Entry):
        if self.ActivePatch == None:
            raise Exception("No patch exists, please create one first")
        self.ActivePatch.AddEntry(Entry)

    def AddEntryToPatch(self, FileID, TypeID):
        if self.ActivePatch == None:
            raise Exception("No patch exists, please create one first")

        Entry = self.GetEntry(FileID, TypeID)
        if Entry != None:
            PatchEntry = deepcopy(Entry)
            if PatchEntry.IsSelected:
                self.SelectEntries([PatchEntry], True)
            self.ActivePatch.AddEntry(PatchEntry)
            return PatchEntry
        return None

    def RemoveEntryFromPatch(self, FileID, TypeID):
        if self.ActivePatch != None:
            self.ActivePatch.RemoveEntry(FileID, TypeID)
        return None

    def GetPatchEntry(self, Entry):
        if self.ActivePatch != None:
            return self.ActivePatch.GetEntry(Entry.FileID, Entry.TypeID)
        return None
    def GetPatchEntry_B(self, FileID, TypeID):
        if self.ActivePatch != None:
            return self.ActivePatch.GetEntry(FileID, TypeID)
        return None

    def IsInPatch(self, Entry):
        if self.ActivePatch != None:
            PatchEntry = self.ActivePatch.GetEntry(Entry.FileID, Entry.TypeID)
            if PatchEntry != None: return True
            else: return False
        return False

    def DuplicateEntry(self, FileID, TypeID, NewID):
        Entry = self.GetEntry(FileID, TypeID)
        if Entry != None:
            self.CopyPaste(Entry, False, NewID)

#endregion

#region Classes and Functions: Stingray Materials
def LoadStingrayAnimation(ID, TocData, GpuData, StreamData, Reload, MakeBlendObject):
    toc = MemoryStream(TocData)
    PrettyPrint("Loading Animation")
    animation = StingrayAnimation()
    animation.Serialize(toc)
    PrettyPrint("Finished Loading Animation")
    if MakeBlendObject: # To-do: create action for armature
        context = bpy.context
        armature = context.active_object
        try:
            bones_id = int(armature['BonesID'])
        except ValueError:
            raise Exception(f"\n\nCould not obtain custom property: BonesID from armature: {armature.name}. Please make sure this is a valid value")
        bones_entry = Global_TocManager.GetEntryByLoadArchive(int(bones_id), BoneID)
        if not bones_entry.IsLoaded:
            bones_entry.Load()
        bones_data = bones_entry.TocData
        animation.to_action(context, armature, bones_data, ID)
    return animation
    
def SaveStingrayAnimation(self, ID, TocData, GpuData, StreamData, Animation):
    toc = MemoryStream(IOMode = "write")
    Animation.Serialize(toc)
    return [toc.Data, b"", b""]

def LoadStingrayMaterial(ID, TocData, GpuData, StreamData, Reload, MakeBlendObject):
    exists = True
    force_reload = False
    try:
        mat = bpy.data.materials[str(ID)]
        force_reload = True
    except: exists = False


    f = MemoryStream(TocData)
    Material = StingrayMaterial()
    Material.Serialize(f)
    if MakeBlendObject and not (exists and not Reload): AddMaterialToBlend(ID, Material, Reload)
    elif force_reload: AddMaterialToBlend(ID, Material, True)
    return Material

def SaveStingrayMaterial(self, ID, TocData, GpuData, StreamData, LoadedData):
    if self.MaterialTemplate != None:
        texturesFilepaths = GenerateMaterialTextures(self)
    mat = LoadedData
    for TexIdx in range(len(mat.TexIDs)):
        if not bpy.context.scene.Hd2ToolPanelSettings.SaveTexturesWithMaterial:
            continue
        oldTexID = mat.TexIDs[TexIdx]
        if mat.DEV_DDSPaths[TexIdx] != None:
            # get texture data
            StingrayTex = StingrayTexture()
            with open(mat.DEV_DDSPaths[TexIdx], 'r+b') as f:
                StingrayTex.FromDDS(f.read())
            Toc = MemoryStream(IOMode="write")
            Gpu = MemoryStream(IOMode="write")
            Stream = MemoryStream(IOMode="write")
            StingrayTex.Serialize(Toc, Gpu, Stream)
            # add texture entry to archive
            Entry = TocEntry()

            TextureID = oldTexID
            if bpy.context.scene.Hd2ToolPanelSettings.GenerateRandomTextureIDs:
                TextureID = RandomHash16()

            Entry.FileID = TextureID
            Entry.TypeID = TexID
            Entry.IsCreated = True
            Entry.SetData(Toc.Data, Gpu.Data, Stream.Data, False)
            Global_TocManager.AddNewEntryToPatch(Entry)
            mat.TexIDs[TexIdx] = TextureID
        else:
            Global_TocManager.Load(int(oldTexID), TexID, False, True)
            Entry = Global_TocManager.GetEntry(int(oldTexID), TexID, True)
            if Entry != None:
                Entry = deepcopy(Entry)

                TextureID = oldTexID
                if bpy.context.scene.Hd2ToolPanelSettings.GenerateRandomTextureIDs:
                    TextureID = RandomHash16()

                Entry.FileID = TextureID
                Entry.IsCreated = True

                ExistingEntry = Global_TocManager.GetEntry(Entry.FileID, Entry.TypeID)
                if ExistingEntry:
                    Global_TocManager.RemoveEntryFromPatch(ExistingEntry.FileID, ExistingEntry.TypeID)

                Global_TocManager.AddNewEntryToPatch(Entry)
                mat.TexIDs[TexIdx] = TextureID
                
        if self.MaterialTemplate != None:
            path = texturesFilepaths[TexIdx]
            if not os.path.exists(path):
                raise Exception(f"Could not find file at path: {path}")
            if not Entry:
                raise Exception(f"Could not find or generate texture entry ID: {int(mat.TexIDs[TexIdx])}")
            
            if path.endswith(".dds"):
                SaveImageDDS(path, Entry.FileID)
            else:
                SaveImagePNG(path, Entry.FileID)
        if bpy.context.scene.Hd2ToolPanelSettings.GenerateRandomTextureIDs:
            Global_TocManager.RemoveEntryFromPatch(oldTexID, TexID)
    f = MemoryStream(IOMode="write")
    LoadedData.Serialize(f)
    return [f.Data, b"", b""]

def AddMaterialToBlend(ID, StingrayMat, EmptyMatExists=False):
    try:
        mat = bpy.data.materials[str(ID)]
        PrettyPrint(f"Found material for ID: {ID} Skipping creation of new material")
        return
    except:
        PrettyPrint(f"Unable to find material in blender scene for ID: {ID} creating new material")
        mat = bpy.data.materials.new(str(ID)); mat.name = str(ID)

    r.seed(ID)
    mat.diffuse_color = (r.random(), r.random(), r.random(), 1)
    mat.use_nodes = True
    #bsdf = mat.node_tree.nodes["Principled BSDF"] # It's not even used?

    Entry = Global_TocManager.GetEntry(int(ID), MaterialID)
    if Entry == None:
        PrettyPrint(f"No Entry Found when getting Material ID: {ID}", "ERROR")
        return
    if Entry.MaterialTemplate != None: CreateAddonMaterial(ID, StingrayMat, mat, Entry)
    else: CreateGameMaterial(StingrayMat, mat)
    
def CreateGameMaterial(StingrayMat, mat):
    for node in mat.node_tree.nodes:
        if node.bl_idname == 'ShaderNodeTexImage':
            mat.node_tree.nodes.remove(node)
    idx = 0
    height = round(len(StingrayMat.TexIDs) * 300 / 2)
    for TextureID in StingrayMat.TexIDs:
        texImage = mat.node_tree.nodes.new('ShaderNodeTexImage')
        texImage.location = (-450, height - 300*idx)

        try:    bpy.data.images[str(TextureID)]
        except: Global_TocManager.Load(TextureID, TexID, False, True)
        try: texImage.image = bpy.data.images[str(TextureID)]
        except:
            PrettyPrint(f"Failed to load texture {TextureID}. This is not fatal, but does mean that the materials in Blender will have empty image texture nodes", "warn")
            pass
        idx +=1

def CreateAddonMaterial(ID, StingrayMat, mat, Entry):
    mat.node_tree.nodes.clear()
    output = mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (200, 300)
    group = mat.node_tree.nodes.new('ShaderNodeGroup')
    treeName = f"{Entry.MaterialTemplate}-{str(ID)}"
    nodeTree = bpy.data.node_groups.new(treeName, 'ShaderNodeTree')
    group.node_tree = nodeTree
    group.location = (0, 300)

    group_input = nodeTree.nodes.new('NodeGroupInput')
    group_input.location = (-400,0)
    group_output = nodeTree.nodes.new('NodeGroupOutput')
    group_output.location = (400,0)

    idx = 0
    height = round(len(StingrayMat.TexIDs) * 300 / 2)
    TextureNodes = []
    for TextureID in StingrayMat.TexIDs:
        texImage = mat.node_tree.nodes.new('ShaderNodeTexImage')
        texImage.location = (-450, height - 300*idx)

        TextureNodes.append(texImage)

        name = TextureTypeLookup[Entry.MaterialTemplate][idx]
        socket_type = "NodeSocketColor"
        nodeTree.interface.new_socket(name=name, in_out ="INPUT", socket_type=socket_type).hide_value = True

        try:    bpy.data.images[str(TextureID)]
        except: Global_TocManager.Load(TextureID, TexID, False, True)
        try: texImage.image = bpy.data.images[str(TextureID)]
        except:
            PrettyPrint(f"Failed to load texture {TextureID}. This is not fatal, but does mean that the materials in Blender will have empty image texture nodes", "warn")
            pass
        
        if "Normal" in name:
            texImage.image.colorspace_settings.name = 'Non-Color'

        mat.node_tree.links.new(texImage.outputs['Color'], group.inputs[idx])
        idx +=1

    nodeTree.interface.new_socket(name="Surface",in_out ="OUTPUT", socket_type="NodeSocketShader")

    nodes = mat.node_tree.nodes
    for node in nodes:
        if node.type == 'BSDF_PRINCIPLED':
            nodes.remove(node)
        elif node.type == 'OUTPUT_MATERIAL':
             mat.node_tree.links.new(group.outputs['Surface'], node.inputs['Surface'])
    
    inputNode = nodeTree.nodes.get('Group Input')
    outputNode = nodeTree.nodes.get('Group Output')
    bsdf = nodeTree.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (50, 0)
    separateColor = nodeTree.nodes.new('ShaderNodeSeparateColor')
    separateColor.location = (-150, 0)
    normalMap = nodeTree.nodes.new('ShaderNodeNormalMap')
    normalMap.location = (-150, -150)

    bsdf.inputs['IOR'].default_value = 1
    bsdf.inputs['Emission Strength'].default_value = 1

    bpy.ops.file.unpack_all(method='REMOVE')
    
    PrettyPrint(f"Setting up any custom templates. Current Template: {Entry.MaterialTemplate}")

    if Entry.MaterialTemplate == "basic": SetupBasicBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap)
    elif Entry.MaterialTemplate == "basic+": SetupBasicBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap)
    elif Entry.MaterialTemplate == "original": SetupOriginalBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap)
    elif Entry.MaterialTemplate == "emissive": SetupEmissiveBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap)
    elif Entry.MaterialTemplate == "alphaclip": SetupAlphaClipBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap, mat)
    elif Entry.MaterialTemplate == "advanced": SetupAdvancedBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap, TextureNodes, group, mat)
    elif Entry.MaterialTemplate == "translucent": SetupTranslucentBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap, mat)
    
def SetupBasicBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap):
    bsdf.inputs['Emission Strength'].default_value = 0
    inputNode.location = (-750, 0)
    SetupNormalMapTemplate(nodeTree, inputNode, normalMap, bsdf)
    nodeTree.links.new(inputNode.outputs['Base Color'], bsdf.inputs['Base Color'])
    nodeTree.links.new(inputNode.outputs['PBR'], separateColor.inputs['Color'])
    nodeTree.links.new(separateColor.outputs['Red'], bsdf.inputs['Metallic'])
    nodeTree.links.new(separateColor.outputs['Green'], bsdf.inputs['Roughness'])
    nodeTree.links.new(bsdf.outputs['BSDF'], outputNode.inputs['Surface'])

def SetupOriginalBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap):
    inputNode.location = (-800, -0)
    SetupNormalMapTemplate(nodeTree, inputNode, normalMap, bsdf)
    nodeTree.links.new(inputNode.outputs['Base Color'], bsdf.inputs['Base Color'])
    nodeTree.links.new(inputNode.outputs['Emission'], bsdf.inputs['Emission Color'])
    nodeTree.links.new(inputNode.outputs['PBR'], separateColor.inputs['Color'])
    nodeTree.links.new(separateColor.outputs['Red'], bsdf.inputs['Metallic'])
    nodeTree.links.new(separateColor.outputs['Green'], bsdf.inputs['Roughness'])
    nodeTree.links.new(bsdf.outputs['BSDF'], outputNode.inputs['Surface'])

def SetupEmissiveBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap):
    nodeTree.links.new(inputNode.outputs['Base Color/Metallic'], bsdf.inputs['Base Color'])
    nodeTree.links.new(inputNode.outputs['Emission'], bsdf.inputs['Emission Color'])
    nodeTree.links.new(inputNode.outputs['Normal/AO/Roughness'], separateColor.inputs['Color'])
    nodeTree.links.new(separateColor.outputs['Red'], normalMap.inputs['Color'])
    nodeTree.links.new(normalMap.outputs['Normal'], bsdf.inputs['Normal'])
    nodeTree.links.new(bsdf.outputs['BSDF'], outputNode.inputs['Surface'])

def SetupAlphaClipBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap, mat):
    bsdf.inputs['Emission Strength'].default_value = 0
    combineColor = nodeTree.nodes.new('ShaderNodeCombineColor')
    combineColor.inputs['Blue'].default_value = 1
    combineColor.location = (-350, -150)
    separateColor.location = (-550, -150)
    inputNode.location = (-750, 0)
    mat.blend_method = 'CLIP'
    nodeTree.links.new(inputNode.outputs['Base Color/Metallic'], bsdf.inputs['Base Color'])
    nodeTree.links.new(inputNode.outputs['Alpha Mask'], bsdf.inputs['Alpha'])
    nodeTree.links.new(inputNode.outputs['Normal/AO/Roughness'], separateColor.inputs['Color'])
    nodeTree.links.new(separateColor.outputs['Red'], combineColor.inputs['Red'])
    nodeTree.links.new(separateColor.outputs['Green'], combineColor.inputs['Green'])
    nodeTree.links.new(combineColor.outputs['Color'], normalMap.inputs['Color'])
    nodeTree.links.new(normalMap.outputs['Normal'], bsdf.inputs['Normal'])
    nodeTree.links.new(bsdf.outputs['BSDF'], outputNode.inputs['Surface'])

def SetupNormalMapTemplate(nodeTree, inputNode, normalMap, bsdf):
    separateColorNormal = nodeTree.nodes.new('ShaderNodeSeparateColor')
    separateColorNormal.location = (-550, -150)
    combineColorNormal = nodeTree.nodes.new('ShaderNodeCombineColor')
    combineColorNormal.location = (-350, -150)
    combineColorNormal.inputs['Blue'].default_value = 1
    nodeTree.links.new(inputNode.outputs['Normal'], separateColorNormal.inputs['Color'])
    nodeTree.links.new(separateColorNormal.outputs['Red'], combineColorNormal.inputs['Red'])
    nodeTree.links.new(separateColorNormal.outputs['Green'], combineColorNormal.inputs['Green'])
    nodeTree.links.new(combineColorNormal.outputs['Color'], normalMap.inputs['Color'])
    nodeTree.links.new(normalMap.outputs['Normal'], bsdf.inputs['Normal'])

def SetupAdvancedBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap, TextureNodes, group, mat):
    bsdf.inputs['Emission Strength'].default_value = 0
    TextureNodes[5].image.colorspace_settings.name = 'Non-Color'
    nodeTree.nodes.remove(separateColor)
    inputNode.location = (-750, 0)
    separateColorNormal = nodeTree.nodes.new('ShaderNodeSeparateColor')
    separateColorNormal.location = (-550, -150)
    combineColorNormal = nodeTree.nodes.new('ShaderNodeCombineColor')
    combineColorNormal.location = (-350, -150)
    combineColorNormal.inputs['Blue'].default_value = 1
    nodeTree.links.new(inputNode.outputs['Normal/AO/Roughness'], separateColorNormal.inputs['Color'])
    nodeTree.links.new(separateColorNormal.outputs['Red'], combineColorNormal.inputs['Red'])
    nodeTree.links.new(separateColorNormal.outputs['Green'], combineColorNormal.inputs['Green'])
    nodeTree.links.new(normalMap.outputs['Normal'], bsdf.inputs['Normal'])
    nodeTree.links.new(combineColorNormal.outputs['Color'], normalMap.inputs['Color'])
    nodeTree.links.new(inputNode.outputs['Color/Emission Mask'], bsdf.inputs['Base Color'])
    nodeTree.links.new(inputNode.outputs['Metallic'], bsdf.inputs['Metallic'])

    RoughnessSocket = nodeTree.interface.new_socket(name="Normal/AO/Roughness (Alpha)", in_out ="INPUT", socket_type="NodeSocketFloat").hide_value = True
    mat.node_tree.links.new(TextureNodes[2].outputs['Alpha'], group.inputs['Normal/AO/Roughness (Alpha)'])
    nodeTree.links.new(inputNode.outputs['Normal/AO/Roughness (Alpha)'], bsdf.inputs['Roughness'])

    multiplyEmission = nodeTree.nodes.new('ShaderNodeMath')
    multiplyEmission.location = (-350, -350)
    multiplyEmission.operation = 'MULTIPLY'
    multiplyEmission.inputs[1].default_value = 0
    nodeTree.interface.new_socket(name="Color/Emission Mask (Alpha)", in_out ="INPUT", socket_type="NodeSocketFloat").hide_value = True
    mat.node_tree.links.new(TextureNodes[5].outputs['Alpha'], group.inputs['Color/Emission Mask (Alpha)'])
    nodeTree.links.new(inputNode.outputs['Color/Emission Mask (Alpha)'], multiplyEmission.inputs[0])
    nodeTree.links.new(multiplyEmission.outputs['Value'], bsdf.inputs['Emission Strength'])
    
    nodeTree.links.new(bsdf.outputs['BSDF'], outputNode.inputs['Surface'])

def SetupTranslucentBlenderMaterial(nodeTree, inputNode, outputNode, bsdf, separateColor, normalMap, mat):
    bsdf.inputs['Emission Strength'].default_value = 0
    nodeTree.nodes.remove(separateColor)
    inputNode.location = (-750, 0)
    SetupNormalMapTemplate(nodeTree, inputNode, normalMap, bsdf)
    nodeTree.links.new(bsdf.outputs['BSDF'], outputNode.inputs['Surface'])
    mat.blend_method = 'BLEND'
    bsdf.inputs['Alpha'].default_value = 0.02
    bsdf.inputs['Base Color'].default_value = (1, 1, 1, 1)

def CreateGenericMaterial(ID, StingrayMat, mat):
    idx = 0
    for TextureID in StingrayMat.TexIDs:
        # Create Node
        texImage = mat.node_tree.nodes.new('ShaderNodeTexImage')
        texImage.location = (-450, 850 - 300*idx)

        # Load Texture
        Global_TocManager.Load(TextureID, TexID, False, True)
        # Apply Texture
        try: texImage.image = bpy.data.images[str(TextureID)]
        except:
            PrettyPrint(f"Failed to load texture {TextureID}. This is not fatal, but does mean that the materials in Blender will have empty image texture nodes", "warn")
            pass
        idx +=1

def GenerateMaterialTextures(Entry):
    material = group = None
    for mat in bpy.data.materials:
        if mat.name == str(Entry.FileID):
            material = mat
            break
    if material == None:
        raise Exception(f"Material Could not be Found ID: {Entry.FileID} {bpy.data.materials}")
    PrettyPrint(f"Found Material {material.name} {material}")
    for node in material.node_tree.nodes:
        if node.type == 'GROUP':
            group = node
            break
    if group == None:
        raise Exception("Could not find node group within material")
    filepaths = []
    for input_socket in group.inputs:
        PrettyPrint(input_socket.name)
        if input_socket.is_linked:
            for link in input_socket.links:
                image = link.from_node.image
                if image.packed_file:
                    raise Exception(f"Image: {image.name} is packed. Please unpack your image.")
                path = bpy.path.abspath(image.filepath)
                PrettyPrint(f"Getting image path at: {path}")
                ID = image.name.split(".")[0]
                if not os.path.exists(path) and ID.isnumeric():
                    PrettyPrint(f"Image not found. Attempting to find image: {ID} in temp folder.", 'WARN')
                    tempdir = tempfile.gettempdir()
                    path = f"{tempdir}\\{ID}.png"
                filepaths.append(path)

                # enforce proper colorspace for abnormal stingray textures
                if "Normal" in input_socket.name or "Color/Emission Mask" in input_socket.name:
                     image.colorspace_settings.name = 'Non-Color'
    
    # display proper emissives on advanced material
    if "advanced" in group.node_tree.name:
        colorVariable = Entry.LoadedData.ShaderVariables[32].values
        emissionColor = (colorVariable[0], colorVariable[1], colorVariable[2], 1)
        emissionStrength = Entry.LoadedData.ShaderVariables[40].values[0]
        emissionStrength = max(0, emissionStrength)
        PrettyPrint(f"Emission color: {emissionColor} Strength: {emissionStrength}")
        for node in group.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                node.inputs['Emission Color'].default_value = emissionColor
            if node.type == 'MATH' and node.operation == 'MULTIPLY':
                node.inputs[1].default_value = emissionStrength

    # update color and alpha of translucent
    if "translucent" in group.node_tree.name:
        colorVariable = Entry.LoadedData.ShaderVariables[7].values
        baseColor = (colorVariable[0], colorVariable[1], colorVariable[2], 1)
        alphaVariable = Entry.LoadedData.ShaderVariables[1].values[0]
        PrettyPrint(f"Base color: {baseColor} Alpha: {alphaVariable}")
        for node in group.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                node.inputs['Base Color'].default_value = baseColor
                node.inputs['Alpha'].default_value = alphaVariable

    PrettyPrint(f"Found {len(filepaths)} Images: {filepaths}")
    return filepaths

#endregion

#region Classes and Functions: Stingray Textures

def BlendImageToStingrayTexture(image, StingrayTex):
    tempdir  = tempfile.gettempdir()
    dds_path = f"{tempdir}\\blender_img.dds"
    tga_path = f"{tempdir}\\blender_img.tga"

    image.file_format = 'TARGA_RAW'
    image.filepath_raw = tga_path
    image.save()

    subprocess.run([Global_texconvpath, "-y", "-o", tempdir, "-ft", "dds", "-dx10", "-f", StingrayTex.Format, "-sepalpha", "-alpha", dds_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    
    if os.path.isfile(dds_path):
        with open(dds_path, 'r+b') as f:
            StingrayTex.FromDDS(f.read())
    else:
        raise Exception("Failed to convert TGA to DDS")

def LoadStingrayTexture(ID, TocData, GpuData, StreamData, Reload, MakeBlendObject):
    exists = True
    try: bpy.data.images[str(ID)]
    except: exists = False

    StingrayTex = StingrayTexture()
    StingrayTex.Serialize(MemoryStream(TocData), MemoryStream(GpuData), MemoryStream(StreamData))
    dds = StingrayTex.ToDDS()

    if MakeBlendObject and not (exists and not Reload):
        tempdir = tempfile.gettempdir()
        dds_path = f"{tempdir}\\{ID}.dds"
        png_path = f"{tempdir}\\{ID}.png"

        with open(dds_path, 'w+b') as f:
            f.write(dds)
        
        subprocess.run([Global_texconvpath, "-y", "-o", tempdir, "-ft", "png", "-f", "R8G8B8A8_UNORM", "-sepalpha", "-alpha", dds_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

        if os.path.isfile(png_path):
            image = bpy.data.images.load(png_path)
            image.name = str(ID)
            image.pack()
        else:
            raise Exception(f"Failed to convert texture {ID} to PNG, or DDS failed to export")
    
    return StingrayTex

def SaveStingrayTexture(self, ID, TocData, GpuData, StreamData, LoadedData):
    exists = True
    try: bpy.data.images[str(ID)]
    except: exists = False

    Toc = MemoryStream(IOMode="write")
    Gpu = MemoryStream(IOMode="write")
    Stream = MemoryStream(IOMode="write")

    LoadedData.Serialize(Toc, Gpu, Stream)

    return [Toc.Data, Gpu.Data, Stream.Data]

#endregion

#region Stingray IO

def LoadStingrayBones(ID, TocData, GpuData, StreamData, Reload, MakeBlendObject):
    StingrayBonesData = StingrayBones(Global_BoneNames)
    StingrayBonesData.Serialize(MemoryStream(TocData))
    return StingrayBonesData

def LoadStingrayCompositeMesh(ID, TocData, GpuData, StreamData, Reload, MakeBlendObject):
    raise Exception("Composite Meshes Are Not Yet Supported")
    StingrayCompositeMeshData = StingrayCompositeMesh()
    StingrayCompositeMeshData.Serialize(MemoryStream(TocData), MemoryStream(GpuData))
    return StingrayCompositeMeshData

def LoadStingrayParticle(ID, TocData, GpuData, StreamData, Reload, MakeBlendObject):
    f = MemoryStream(TocData)
    Particle = StingrayParticles()
    Particle.Serialize(f)
    return Particle

def SaveStingrayParticle(self, ID, TocData, GpuData, StreamData, LoadedData):
    f = MemoryStream(TocData, IOMode="write") # Load in original TocData before overwriting it
    LoadedData.Serialize(f)
    return [f.Data, b"", b""]

def LoadStingrayDump(ID, TocData, GpuData, StreamData, Reload, MakeBlendObject):
    StingrayDumpData = StingrayRawDump()
    StingrayDumpData.Serialize(MemoryStream(TocData))
    return StingrayDumpData

def SaveStingrayDump(self, ID, TocData, GpuData, StreamData, LoadedData):
    Toc = MemoryStream(IOMode="write")
    Gpu = MemoryStream(IOMode="write")
    Stream = MemoryStream(IOMode="write")

    LoadedData.Serialize(Toc, Gpu, Stream)

    return [Toc.Data, Gpu.Data, Stream.Data]

def LoadStingrayMesh(ID, TocData, GpuData, StreamData, Reload, MakeBlendObject, LoadMaterialSlotNames=False):
    toc  = MemoryStream(TocData)
    gpu  = MemoryStream(GpuData)
        
    bones_entry = Global_TocManager.GetEntryByLoadArchive(int(ID), int(BoneID))
    if bones_entry and not bones_entry.IsLoaded:
        bones_entry.Load(False, False)
    StingrayMesh = StingrayMeshFile()
    StingrayMesh.NameHash = int(ID)
    StingrayMesh.LoadMaterialSlotNames = LoadMaterialSlotNames
    StingrayMesh.Serialize(toc, gpu, Global_TocManager)
    if MakeBlendObject: CreateModel(StingrayMesh, str(ID), Global_BoneNames)
    return StingrayMesh

def SaveStingrayMesh(self, ID, TocData, GpuData, StreamData, StingrayMesh, BlenderOpts=None):
    if BlenderOpts and BlenderOpts.get("AutoLods"):
        lod0 = None
        for mesh in StingrayMesh.RawMeshes:
            if mesh.LodIndex == 0:
                lod0 = mesh
                break
        # print(lod0)
        if lod0 != None:
            for n in range(len(StingrayMesh.RawMeshes)):
                if StingrayMesh.RawMeshes[n].IsLod():
                    newmesh = copy.copy(lod0)
                    newmesh.MeshInfoIndex = StingrayMesh.RawMeshes[n].MeshInfoIndex
                    StingrayMesh.RawMeshes[n] = newmesh
    toc  = MemoryStream(IOMode = "write")
    gpu  = MemoryStream(IOMode = "write")
    StingrayMesh.Serialize(toc, gpu, Global_TocManager, BlenderOpts=BlenderOpts)
    return [toc.Data, gpu.Data, b""]

#endregion

#region Operators: Archives & Patches

def ArchivesNotLoaded(self):
    if len(Global_TocManager.LoadedArchives) <= 0:
        self.report({'ERROR'}, "No Archives Currently Loaded")
        return True
    else: 
        return False
    
def PatchesNotLoaded(self):
    if len(Global_TocManager.Patches) <= 0:
        self.report({'ERROR'}, "No Patches Currently Loaded")
        return True
    else:
        return False

def ObjectHasModifiers(self, objects):
    for obj in objects:
        for modifier in obj.modifiers:
            if modifier.type != "ARMATURE":
                self.report({'ERROR'}, f"Object: {obj.name} has {len(obj.modifiers)} unapplied modifiers")
                return True
    return False

def ObjectHasShapeKeys(self, objects):
    for obj in objects:
        if hasattr(obj.data.shape_keys, 'key_blocks'):
            self.report({'ERROR'}, f"Object: {obj.name} has {len(obj.data.shape_keys.key_blocks)} unapplied shape keys")
            return True
    return False

def MaterialsNumberNames(self, objects):
    mesh_objs = [ob for ob in objects if ob.type == 'MESH']
    for mesh in mesh_objs:
        invalidMaterials = 0
        if len(mesh.material_slots) == 0:
            self.report({'ERROR'}, f"Object: {mesh.name} has no material slots")
            return True
        for slot in mesh.material_slots:
            if slot.material:
                materialName = slot.material.name
                if not materialName.isnumeric() and materialName != "StingrayDefaultMaterial":
                    invalidMaterials += 1
            else:
                invalidMaterials += 1
        if invalidMaterials > 0:
            self.report({'ERROR'}, f"Object: {mesh.name} has {invalidMaterials} non Helldivers 2 Materials")
            return True
    return False

def HasZeroVerticies(self, objects):
    mesh_objs = [ob for ob in objects if ob.type == 'MESH']
    for mesh in mesh_objs:
        verts = len(mesh.data.vertices)
        PrettyPrint(f"Object: {mesh.name} Verticies: {verts}")
        if verts <= 0:
            self.report({'ERROR'}, f"Object: {mesh.name} has no zero verticies")
            return True
    return False

def MeshNotValidToSave(self):
    objects = bpy.context.selected_objects
    for i, obj in enumerate(objects):
        if obj.type != 'MESH':
            objects.pop(i)

    return (PatchesNotLoaded(self) or 
            CheckDuplicateIDsInScene(self, objects) or 
            CheckVertexGroups(self, objects) or 
            ObjectHasModifiers(self, objects) or 
            MaterialsNumberNames(self, objects) or 
            HasZeroVerticies(self, objects) or 
            ObjectHasShapeKeys(self, objects) or 
            CheckHaveHD2Properties(self, objects)
            )

def CheckHaveHD2Properties(self, objects):
    list_copy = list(objects)
    for obj in list_copy:
        try:
            _ = obj["Z_ObjectID"]
            _ = obj["MeshInfoIndex"]
            _ = obj["BoneInfoIndex"]
        except KeyError:
            self.report({'ERROR'}, f"Object {obj.name} is missing HD2 properties")
            return True
    return False


def CheckDuplicateIDsInScene(self, objects):
    custom_objects = {}
    for obj in objects:
        obj_id = obj.get("Z_ObjectID")
        swap_id = obj.get("Z_SwapID")
        mesh_index = obj.get("MeshInfoIndex")
        bone_index = obj.get("BoneInfoIndex")
        if obj_id is not None:
            obj_tuple = (obj_id, mesh_index, bone_index, swap_id)
            try:
                custom_objects[obj_tuple].append(obj)
            except:
                custom_objects[obj_tuple] = [obj]
    for item in custom_objects.values():
        if len(item) > 1:
            self.report({'ERROR'}, f"Multiple objects with the same HD2 properties are in the scene! Please delete one and try again.\nObjects: {', '.join([obj.name for obj in item])}")
            return True
    return False


def CheckVertexGroups(self, objects):
    list_copy = list(objects)
    for obj in list_copy:
        incorrectGroups = 0
        try:
            BoneIndex = obj["BoneInfoIndex"]
        except KeyError:
            self.report({'ERROR'}, f"Couldn't find HD2 Properties in {obj.name}")
            return True
        if len(obj.vertex_groups) <= 0 and BoneIndex != -1:
            self.report({'ERROR'}, f"No Vertex Groups Found for non-static mesh: {obj.name}")
            return True
        if len(obj.vertex_groups) > 0 and BoneIndex == -1:
            self.report({'ERROR'}, f"Vertex Groups Found for static mesh: {obj.name}. Please remove vertex groups.")
            return True
        if bpy.context.scene.Hd2ToolPanelSettings.LegacyWeightNames:
            for group in obj.vertex_groups:
                if "_" not in group.name:
                    incorrectGroups += 1
                else:
                    parts = group.name.split("_")
                    if parts[1] is None or not parts[0].isnumeric() or not parts[1].isnumeric():
                        incorrectGroups += 1
        if incorrectGroups > 0:
            self.report({'ERROR'}, f"Found {incorrectGroups} Incorrect Vertex Group Name Scheming for Legacy Weight Names for Object: {obj.name}")
            return True
    return False

def CopyToClipboard(txt):
    cmd='echo '+txt.strip()+'|clip'
    return subprocess.check_call(cmd, shell=True)

def hex_to_decimal(hex_string):
    try:
        decimal_value = int(hex_string, 16)
        return decimal_value
    except ValueError:
        PrettyPrint(f"Invalid hexadecimal string: {hex_string}")

class ChangeFilepathOperator(Operator, ImportHelper):
    bl_label = "Change Filepath"
    bl_idname = "helldiver2.change_filepath"
    bl_description = "Change the game's data folder directory"
    #filename_ext = "."
    use_filter_folder = True

    filter_glob: StringProperty(options={'HIDDEN'}, default='')

    def __init__(self):
        global Global_gamepath
        self.filepath = bpy.path.abspath(Global_gamepath)
        
    def execute(self, context):
        global Global_gamepath
        global Global_gamepathIsValid
        filepath = self.filepath
        steamapps = "steamapps"
        if steamapps in filepath:
            filepath = f"{filepath.partition(steamapps)[0]}steamapps\common\Helldivers 2\data\ "[:-1]
        else:
            self.report({'ERROR'}, f"Could not find steamapps folder in filepath: {filepath}")
            return{'CANCELLED'}
        Global_gamepath = filepath
        UpdateConfig()
        PrettyPrint(f"Changed Game File Path: {Global_gamepath}")
        Global_gamepathIsValid = True
        return{'FINISHED'}
    
class ChangeSearchpathOperator(Operator, ImportHelper):
    bl_label = "Change Searchpath"
    bl_idname = "helldiver2.change_searchpath"
    bl_description = "Change the output directory for searching by entry ID"
    use_filter_folder = True

    filter_glob: StringProperty(options={'HIDDEN'}, default='')

    def __init__(self):
        global Global_searchpath
        self.filepath = bpy.path.abspath(Global_searchpath)
        
    def execute(self, context):
        global Global_searchpath
        Global_searchpath = self.filepath
        UpdateConfig()
        PrettyPrint(f"Changed Game Search Path: {Global_searchpath}")
        return{'FINISHED'}

class DefaultLoadArchiveOperator(Operator):
    bl_label = "Default Archive"
    bl_description = "Loads the Default Archive that Patches should be built upon"
    bl_idname = "helldiver2.archive_import_default"

    def execute(self, context):
        path = Global_gamepath + BaseArchiveHexID
        if not os.path.exists(path):
            self.report({'ERROR'}, "Current Filepath is Invalid. Change this in the Settings")
            context.scene.Hd2ToolPanelSettings.MenuExpanded = True
            return{'CANCELLED'}
        Global_TocManager.LoadArchive(path, True, False)

        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()
        
        return{'FINISHED'}
      
class LoadArchiveOperator(Operator, ImportHelper):
    bl_label = "Manually Load Archive"
    bl_idname = "helldiver2.archive_import"
    bl_description = "Loads a Selected Archive from Helldivers Data Folder"

    files: CollectionProperty(type=bpy.types.OperatorFileListElement,options={"HIDDEN", "SKIP_SAVE"})
    is_patch: BoolProperty(name="is_patch", default=False, options={'HIDDEN'})
    #files = CollectionProperty(name='File paths', type=bpy.types.PropertyGroup)

    def __init__(self):
        self.filepath = bpy.path.abspath(Global_gamepath)

    def execute(self, context):
        # Sanitize path by removing any provided extension, so the correct TOC file is loaded
        if not self.is_patch:
            filepaths = [Global_gamepath + f.name for f in self.files]
        else:
            if ".patch" not in self.filepath:
                self.report({'ERROR'}, f"Selected path: {self.filepath} is not a patch file! Please make sure to select the patch files. If you selected a zip file, please extract the contents and select the patch files actual patch files.")
                return {'CANCELLED'}
            filepaths = [self.filepath, ]
        oldLoadedLength = len(Global_TocManager.LoadedArchives)
        for filepath in filepaths:
            if not os.path.exists(filepath) or filepath.endswith(".ini") or filepath.endswith(".data"):
                continue
            path = Path(filepath)
            if not path.suffix.startswith(".patch_"): path = path.with_suffix("")

            archiveToc = Global_TocManager.LoadArchive(str(path), True, self.is_patch)
        PrettyPrint(f"Loaded {len(Global_TocManager.LoadedArchives) - oldLoadedLength} Archive(s)")

        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()
        
        return{'FINISHED'}

class UnloadArchivesOperator(Operator):
    bl_label = "Unload Archives"
    bl_idname = "helldiver2.archive_unloadall"
    bl_description = "Unloads All Current Loaded Archives"

    def execute(self, context):
        Global_TocManager.UnloadArchives()
        return{'FINISHED'}
    
class UnloadPatchesOperator(Operator):
    bl_label = "Unload Patches"
    bl_idname = "helldiver2.patches_unloadall"
    bl_description = "Unloads All Current Loaded Patches"

    def execute(self, context):
        Global_TocManager.UnloadPatches()
        return{'FINISHED'}
    
class BulkLoadOperator(Operator, ImportHelper):
    bl_label = "Bulk Loader"
    bl_idname = "helldiver2.bulk_load"
    bl_description = "Loads archives from a list of patch names in a text file"

    open_file_browser: BoolProperty(default=True, options={'HIDDEN'})
    file: StringProperty(options={'HIDDEN'})
    
    filter_glob: StringProperty(options={'HIDDEN'}, default='*.txt')

    def execute(self, context):
        self.file = self.filepath
        f = open(self.file, "r")
        entries = f.read().splitlines()
        numEntries = len(entries)
        PrettyPrint(f"Loading {numEntries} Archives")
        numArchives = len(Global_TocManager.LoadedArchives)
        entryList = (Global_gamepath + entry.split(" ")[0] for entry in entries)
        Global_TocManager.BulkLoad(entryList)
        numArchives = len(Global_TocManager.LoadedArchives) - numArchives
        numSkipped = numEntries - numArchives
        PrettyPrint(f"Loaded {numArchives} Archives. Skipped {numSkipped} Archives")
        PrettyPrint(f"{len(entries)} {entries}")
        archivesList = (archive.Name for archive in Global_TocManager.LoadedArchives)
        for item in archivesList:
            if item in entries:
                PrettyPrint(f"Switching To First Loaded Archive: {item}")
                bpy.context.scene.Hd2ToolPanelSettings.LoadedArchives = item
                break
        return{'FINISHED'}

class SearchByEntryIDOperator(Operator, ImportHelper):
    bl_label = "Bulk Search By Entry ID"
    bl_idname = "helldiver2.search_by_entry"
    bl_description = "Search for Archives by their contained Entry IDs"

    filter_glob: StringProperty(options={'HIDDEN'}, default='*.txt')

    def execute(self, context):
        baseArchivePath = Global_gamepath + BaseArchiveHexID
        Global_TocManager.LoadArchive(baseArchivePath)
        
        findme = open(self.filepath, "r")
        fileIDs = findme.read().splitlines()
        findme.close()

        archives = []
        PrettyPrint(f"Searching for {len(fileIDs)} IDs")
        for fileID in fileIDs:
            ID = fileID.split()[0]
            try:
                name = fileID.split(" ", 1)[1]
            except:
                name = None
            if ID.upper() != ID.lower():
                ID = hex_to_decimal(ID)
            ID = int(ID)
           
            Archives = SearchByEntryID(ID)
            
            if Archives and bpy.context.scene.Hd2ToolPanelSettings.LoadFoundArchives:
                for Archive in Archives:
                    Global_TocManager.LoadArchive(Archive.Path, True, False)

        curenttime = str(datetime.datetime.now()).replace(":", "-").replace(".", "_")
        outputfile = f"{Global_searchpath}output_{curenttime}.txt"
        PrettyPrint(f"Found {len(archives)} archives")
        output = open(outputfile, "w")
        for item in archives:
            PrettyPrint(item)
            output.write(item + "\n")
        output.close()
        self.report({'INFO'}, f"Found {len(archives)} archives with matching IDs.")
        PrettyPrint(f"Output file created at: {outputfile}")
        return {'FINISHED'}

class SearchByEntryIDInput(Operator):
    bl_label = "Search By Entry ID"
    bl_idname = "helldiver2.search_by_entry_input"
    bl_description = "Search for Archives by their contained Entry IDs"

    entry_id: StringProperty(name="Entry ID")
    def execute(self, context):
            Archives = SearchByEntryID(int(self.entry_id))
            for Archive in Archives:
                Global_TocManager.LoadArchive(Archive.Path)

            # Redraw
            for area in context.screen.areas:
                if area.type == "VIEW_3D": area.tag_redraw()
            
            return{'FINISHED'}
    
    def invoke(self, context, event):
        if ArchivesNotLoaded(self):
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "entry_id")

def SearchByEntryID(ID: int):
    global Global_TocManager
    archives = []
    PrettyPrint(f"Searching for ID: {ID}")
    for Archive in Global_TocManager.SearchArchives:
        if ID in Archive.fileIDs:
            PrettyPrint(f"Found ID: {ID} in Archive: {Archive.Name}")
            archives.append(Archive)
        
    PrettyPrint(f"Found ID: {ID} in {len(archives)} unique archives")
    PrettyPrint(archives)
    return archives

class CreatePatchFromActiveOperator(Operator):
    bl_label = "Create Patch"
    bl_idname = "helldiver2.archive_createpatch"
    bl_description = "Creates Patch from Current Active Archive"

    def execute(self, context):
        
        if bpy.context.scene.Hd2ToolPanelSettings.PatchBaseArchiveOnly:
            baseArchivePath = Global_gamepath + BaseArchiveHexID
            Global_TocManager.LoadArchive(baseArchivePath)
            Global_TocManager.SetActiveByName(BaseArchiveHexID)
        else:
            self.report({'WARNING'}, f"Patch Created Was Not From Base Archive.")
        
        if ArchivesNotLoaded(self):
            return{'CANCELLED'}
        
        Global_TocManager.CreatePatchFromActive()

        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()
        
        return{'FINISHED'}
    
class PatchArchiveOperator(Operator):
    bl_label = "Patch Archive"
    bl_idname = "helldiver2.archive_export"
    bl_description = "Writes Patch to Current Active Patch"

    def execute(self, context):
        global Global_TocManager
        if PatchesNotLoaded(self):
            return{'CANCELLED'}
        
        
        #bpy.ops.wm.save_as_mainfile(filepath=)
        
        if bpy.context.scene.Hd2ToolPanelSettings.SaveUnsavedOnWrite:
            SaveUnsavedEntries(self)
        Global_TocManager.PatchActiveArchive()
        self.report({'INFO'}, f"Patch Written")
        return{'FINISHED'}

class RenamePatchOperator(Operator):
    bl_label = "Rename Mod"
    bl_idname = "helldiver2.rename_patch"
    bl_description = "Change Name of Current Mod Within the Tool"

    patch_name: StringProperty(name="Mod Name")

    def execute(self, context):
        if PatchesNotLoaded(self):
            return{'CANCELLED'}
        
        Global_TocManager.ActivePatch.LocalName = self.patch_name

        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()
        
        return{'FINISHED'}
    
    def invoke(self, context, event):
        if Global_TocManager.ActiveArchive == None:
            self.report({"ERROR"}, "No patch exists, please create one first")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "patch_name")

class ExportPatchAsZipOperator(Operator, ExportHelper):
    bl_label = "Export Patch"
    bl_idname = "helldiver2.export_patch"
    bl_description = "Exports the Current Active Patch as a Zip File"
    
    filename_ext = ".zip"
    use_filter_folder = True
    filter_glob: StringProperty(default='*.zip', options={'HIDDEN'})

    def execute(self, context):
        if PatchesNotLoaded(self):
            return {'CANCELLED'}
        
        filepath = self.properties.filepath
        outputFilename = filepath.replace(".zip", "")
        exportname = filepath.split(Global_backslash)[-1]
        
        patchName = Global_TocManager.ActivePatch.Name
        tempPatchFolder = bpy.app.tempdir + "patchExport\\"
        tempPatchFile = f"{tempPatchFolder}\{patchName}"
        PrettyPrint(f"Exporting in temp folder: {tempPatchFolder}")

        if not os.path.exists(tempPatchFolder):
            os.makedirs(tempPatchFolder)
        Global_TocManager.ActivePatch.ToFile(tempPatchFile)
        shutil.make_archive(outputFilename, 'zip', tempPatchFolder)
        for file in os.listdir(tempPatchFolder):
            path = f"{tempPatchFolder}\{file}"
            os.remove(path)
        os.removedirs(tempPatchFolder)

        if os.path.exists(filepath):
            self.report({'INFO'}, f"{patchName} Exported Successfully As {exportname}")
        else: 
            self.report({'ERROR'}, f"Failed to Export {patchName}")

        return {'FINISHED'}
    
class NextArchiveOperator(Operator):
    bl_label = "Next Archive"
    bl_idname = "helldiver2.next_archive"
    bl_description = "Select the next archive in the list of loaded archives"

    def execute(self, context):
        for index in range(len(Global_TocManager.LoadedArchives)):
            if Global_TocManager.LoadedArchives[index] == Global_TocManager.ActiveArchive:
                nextIndex = min(len(Global_TocManager.LoadedArchives) - 1, index + 1)
                bpy.context.scene.Hd2ToolPanelSettings.LoadedArchives = Global_TocManager.LoadedArchives[nextIndex].Name
                return {'FINISHED'}
        return {'CANCELLED'}
#endregion

#region Operators: Entries

class ArchiveEntryOperator(Operator):
    bl_label  = "Archive Entry"
    bl_idname = "helldiver2.archive_entry"

    object_id: StringProperty()
    object_typeid: StringProperty()
    def execute(self, context):
        return{'FINISHED'}

    def invoke(self, context, event):
        Entry = Global_TocManager.GetEntry(int(self.object_id), int(self.object_typeid))
        if event.ctrl:
            if Entry.IsSelected:
                Global_TocManager.DeselectEntries([Entry])
            else:
                Global_TocManager.SelectEntries([Entry], True)
            return {'FINISHED'}
        if event.shift:
            if Global_TocManager.LastSelected != None:
                LastSelected = Global_TocManager.LastSelected
                StartIndex   = LastSelected.DEV_DrawIndex
                EndIndex     = Entry.DEV_DrawIndex
                Global_TocManager.DeselectAll()
                Global_TocManager.LastSelected = LastSelected
                if StartIndex > EndIndex:
                    Global_TocManager.SelectEntries(Global_TocManager.DrawChain[EndIndex:StartIndex+1], True)
                else:
                    Global_TocManager.SelectEntries(Global_TocManager.DrawChain[StartIndex:EndIndex+1], True)
            else:
                Global_TocManager.SelectEntries([Entry], True)
            return {'FINISHED'}

        Global_TocManager.SelectEntries([Entry])
        return {'FINISHED'}
    
class MaterialTextureEntryOperator(Operator):
    bl_label  = "Texture Entry"
    bl_idname = "helldiver2.material_texture_entry"

    object_id: StringProperty()
    object_typeid: StringProperty()

    texture_index: StringProperty()
    material_id: StringProperty()

    def execute(self, context):
        return{'FINISHED'}

    def invoke(self, context, event):
        return {'FINISHED'}
    
class MaterialShaderVariableEntryOperator(Operator):
    bl_label = "Shader Variable"
    bl_idname = "helldiver2.material_shader_variable"
    bl_description = "Material Shader Variable"

    object_id: StringProperty()
    variable_index: bpy.props.IntProperty()
    value_index: bpy.props.IntProperty()
    value: bpy.props.FloatProperty(
        name="Variable Value",
        description="Enter a floating point number"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "value")

    def execute(self, context):
        Entry = Global_TocManager.GetEntry(self.object_id, MaterialID)
        if Entry:
            Entry.LoadedData.ShaderVariables[self.variable_index].values[self.value_index] = self.value
            PrettyPrint(f"Set value to: {self.value} at variable: {self.variable_index} value: {self.value_index} for material ID: {self.object_id}")
        else:
            self.report({'ERROR'}, f"Could not find entry for ID: {self.object_id}")
            return {'CANCELLED'}
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
class MaterialShaderVariableColorEntryOperator(Operator):
    bl_label = "Color Picker"
    bl_idname = "helldiver2.material_shader_variable_color"
    bl_description = "Material Shader Variable Color"

    object_id: StringProperty()
    variable_index: bpy.props.IntProperty()
    color: bpy.props.FloatVectorProperty(
                name=f"Color",
                subtype="COLOR",
                size=3,
                min=0.0,
                max=1.0,
                default=(1.0, 1.0, 1.0)
            )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "color")

    def execute(self, context):
        Entry = Global_TocManager.GetEntry(self.object_id, MaterialID)
        if Entry:
            for idx in range(3):
                Entry.LoadedData.ShaderVariables[self.variable_index].values[idx] = self.color[idx]
            PrettyPrint(f"Set color to: {self.color}for material ID: {self.object_id}")
        else:
            self.report({'ERROR'}, f"Could not find entry for ID: {self.object_id}")
            return {'CANCELLED'}
        
        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()

        return {'FINISHED'}
    
    def invoke(self, context, event):
        Entry = Global_TocManager.GetEntry(self.object_id, MaterialID)
        if Entry:
            for idx in range(3):
                self.color[idx] = Entry.LoadedData.ShaderVariables[self.variable_index].values[idx]
        else:
            self.report({'ERROR'}, f"Could not find entry for ID: {self.object_id}")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self)

class AddEntryToPatchOperator(Operator):
    bl_label = "Add To Patch"
    bl_idname = "helldiver2.archive_addtopatch"
    bl_description = "Adds Entry into Patch"

    object_id: StringProperty()
    object_typeid: StringProperty()
    def execute(self, context):
        if PatchesNotLoaded(self):
            return{'CANCELLED'}
        
        Entries = EntriesFromStrings(self.object_id, self.object_typeid)
        for Entry in Entries:
            Global_TocManager.AddEntryToPatch(Entry.FileID, Entry.TypeID)
        return{'FINISHED'}

class RemoveEntryFromPatchOperator(Operator):
    bl_label = "Remove Entry From Patch"
    bl_idname = "helldiver2.archive_removefrompatch"

    object_id: StringProperty()
    object_typeid: StringProperty()
    def execute(self, context):
        Entries = EntriesFromStrings(self.object_id, self.object_typeid)
        for Entry in Entries:
            Global_TocManager.RemoveEntryFromPatch(Entry.FileID, Entry.TypeID)
        LoadEntryLists()
        return{'FINISHED'}

class UndoArchiveEntryModOperator(Operator):
    bl_label = "Remove Modifications"
    bl_idname = "helldiver2.archive_undo_mod"

    object_id: StringProperty()
    object_typeid: StringProperty()
    def execute(self, context):
        Entries = EntriesFromStrings(self.object_id, self.object_typeid)
        for Entry in Entries:
            if Entry != None:
                Entry.UndoModifiedData()
        return{'FINISHED'}

class DuplicateEntryOperator(Operator):
    bl_label = "Duplicate Entry"
    bl_idname = "helldiver2.archive_duplicate"
    bl_description = "Duplicate Selected Entry"

    NewFileID : StringProperty(name="NewFileID", default="")
    def draw(self, context):
        global Global_randomID
        PrettyPrint(f"Got ID: {Global_randomID}")
        self.NewFileID = Global_randomID
        layout = self.layout; row = layout.row()
        row.operator("helldiver2.generate_random_id", icon="FILE_REFRESH")
        row = layout.row()
        row.prop(self, "NewFileID", icon='COPY_ID')

    object_id: StringProperty()
    object_typeid: StringProperty()
    def execute(self, context):
        global Global_randomID
        if Global_TocManager.ActivePatch == None:
            Global_randomID = ""
            self.report({'ERROR'}, "No Patches Currently Loaded")
            return {'CANCELLED'}
        if self.NewFileID == "":
            self.report({'ERROR'}, "No ID was given")
            return {'CANCELLED'}
        Global_TocManager.DuplicateEntry(int(self.object_id), int(self.object_typeid), int(self.NewFileID))
        Global_randomID = ""
        return{'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)
    
class GenerateEntryIDOperator(Operator):
    bl_label = "Generate Random ID"
    bl_idname = "helldiver2.generate_random_id"
    bl_description = "Generates a random ID for the entry"

    def execute(self, context):
        global Global_randomID
        Global_randomID = str(RandomHash16())
        PrettyPrint(f"Generated random ID: {Global_randomID}")
        return{'FINISHED'}

class RenamePatchEntryOperator(Operator):
    bl_label = "Rename Entry"
    bl_idname = "helldiver2.archive_entryrename"

    NewFileID : StringProperty(name="NewFileID", default="")
    def draw(self, context):
        layout = self.layout; row = layout.row()
        row.prop(self, "NewFileID", icon='COPY_ID')

    object_id: StringProperty()
    object_typeid: StringProperty()

    material_id: StringProperty(default="")
    texture_index: StringProperty(default="")
    def execute(self, context):
        Entry = Global_TocManager.GetPatchEntry_B(int(self.object_id), int(self.object_typeid))
        if Entry == None and self.material_id == "":
            raise Exception(f"Entry does not exist in patch (cannot rename non patch entries) ID: {self.object_id} TypeID: {self.object_typeid}")
        if Entry != None and self.NewFileID != "":
            Entry.FileID = int(self.NewFileID)

        # Are we renaming via a texture entry in a material?
        if self.material_id != "" and self.texture_index != "":
            MaterialEntry = Global_TocManager.GetPatchEntry_B(int(self.material_id), int(MaterialID))
            MaterialEntry.LoadedData.TexIDs[int(self.texture_index)] = int(self.NewFileID)

        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()
            
        return{'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

class DumpArchiveObjectOperator(Operator):
    bl_label = "Dump Archive Object"
    bl_idname = "helldiver2.archive_object_dump_export"
    bl_description = "Dumps Entry's Contents"

    directory: StringProperty(name="Outdir Path",description="dump output dir")
    filter_folder: BoolProperty(default=True,options={"HIDDEN"})

    object_id: StringProperty(options={"HIDDEN"})
    object_typeid: StringProperty(options={"HIDDEN"})
    def execute(self, context):
        Entries = EntriesFromStrings(self.object_id, self.object_typeid)
        for Entry in Entries:
            if Entry != None:
                data = Entry.GetData()
                FileName = str(Entry.FileID)+"."+GetTypeNameFromID(Entry.TypeID)
                with open(self.directory + FileName, 'w+b') as f:
                    f.write(data[0])
                if data[1] != b"":
                    with open(self.directory + FileName+".gpu", 'w+b') as f:
                        f.write(data[1])
                if data[2] != b"":
                    with open(self.directory + FileName+".stream", 'w+b') as f:
                        f.write(data[2])
        return{'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class ImportDumpOperator(Operator, ImportHelper):
    bl_label = "Import Dump"
    bl_idname = "helldiver2.archive_object_dump_import"
    bl_description = "Loads Raw Dump"

    object_id: StringProperty(options={"HIDDEN"})
    object_typeid: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        if PatchesNotLoaded(self):
            return {'CANCELLED'}

        Entries = EntriesFromStrings(self.object_id, self.object_typeid)
        for Entry in Entries:
            ImportDump(self, Entry, self.filepath)

        return{'FINISHED'}

class ImportDumpByIDOperator(Operator, ImportHelper):
    bl_label = "Import Dump by Entry ID"
    bl_idname = "helldiver2.archive_object_dump_import_by_id"
    bl_description = "Loads Raw Dump over matching entry IDs"

    directory: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE', 'HIDDEN'})
    files: CollectionProperty(type=OperatorFileListElement, options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        if PatchesNotLoaded(self):
            return {'CANCELLED'}

        for file in self.files:
            filepath = self.directory + file.name
            fileID = file.name.split('.')[0]
            typeString = file.name.split('.')[1]
            typeID = GetIDFromTypeName(typeString)

            if typeID == None:
                self.report({'ERROR'}, f"File: {file.name} has no proper file extension for typing")
                return {'CANCELLED'}
            
            if os.path.exists(filepath):
                PrettyPrint(f"Found file: {filepath}")
            else:
                self.report({'ERROR'}, f"Filepath for selected file: {filepath} was not found")
                return {'CANCELLED'}

            entry = Global_TocManager.GetEntryByLoadArchive(int(fileID), int(typeID))
            if entry == None:
                self.report({'ERROR'}, f"Entry for fileID: {fileID} typeID: {typeID} can not be found. Make sure the fileID of your file is correct.")
                return {'CANCELLED'}
            
            ImportDump(self, entry, filepath)
            
        return{'FINISHED'}

def ImportDump(self: Operator, Entry: TocEntry, filepath: str):
    if Entry != None:
        if not Entry.IsLoaded: Entry.Load(False, False)
        path = filepath
        GpuResourchesPath = f"{path}.gpu"
        StreamPath = f"{path}.stream"

        with open(path, 'r+b') as f:
            Entry.TocData = f.read()

        if os.path.isfile(GpuResourchesPath):
            with open(GpuResourchesPath, 'r+b') as f:
                Entry.GpuData = f.read()
        else:
            Entry.GpuData = b""

        if os.path.isfile(StreamPath):
            with open(StreamPath, 'r+b') as f:
                Entry.StreamData = f.read()
        else:
            Entry.StreamData = b""

        Entry.IsModified = True
        if not Global_TocManager.IsInPatch(Entry):
            Global_TocManager.AddEntryToPatch(Entry.FileID, Entry.TypeID)
            
        self.report({'INFO'}, f"Imported Raw Dump: {path}")
    

#endregion

#region Operators: Meshes

class ImportStingrayMeshOperator(Operator):
    bl_label = "Import Archive Mesh"
    bl_idname = "helldiver2.archive_mesh_import"
    bl_description = "Loads Mesh into Blender Scene"

    object_id: StringProperty()
    def execute(self, context):
        EntriesIDs = IDsFromString(self.object_id)
        Errors = []
        for EntryID in EntriesIDs:
            if len(EntriesIDs) == 1:
                Global_TocManager.Load(EntryID, MeshID)
            else:
                # try:
                Global_TocManager.Load(EntryID, MeshID)
                # except Exception as error:
                #     Errors.append([EntryID, error])

        # if len(Errors) > 0:
        #     PrettyPrint("\nThese errors occurred while attempting to load meshes...", "error")
        #     idx = 0
        #     for error in Errors:
        #         PrettyPrint(f"  Error {idx}: for mesh {error[0]}", "error")
        #         PrettyPrint(f"    {error[1]}\n", "error")
        #         idx += 1
        #     raise Exception("One or more meshes failed to load")
        return{'FINISHED'}

class SaveStingrayMeshOperator(Operator):
    bl_label  = "Save Mesh"
    bl_idname = "helldiver2.archive_mesh_save"
    bl_description = "Saves Mesh"
    bl_options = {'REGISTER', 'UNDO'} 

    object_id: StringProperty()
    def execute(self, context):
        mode = context.mode
        if mode != 'OBJECT':
            self.report({'ERROR'}, f"You are Not in OBJECT Mode. Current Mode: {mode}")
            return {'CANCELLED'}
        if MeshNotValidToSave(self):
            return {'CANCELLED'}
        object = None
        object = bpy.context.active_object
        if object == None:
            self.report({"ERROR"}, "No Object selected. Please select the object to be saved.")
            return {'CANCELLED'}
        try:
            ID = object["Z_ObjectID"]
        except:
            self.report({'ERROR'}, f"{object.name} has no HD2 custom properties")
            return{'CANCELLED'}
        SwapID = ""
        try:
            SwapID = object["Z_SwapID"]
            if SwapID != "" and not SwapID.isnumeric():
                self.report({"ERROR"}, f"Object: {object.name} has an incorrect Swap ID. Assure that the ID is a proper integer entry ID.")
                return {'CANCELLED'}
        except:
            self.report({'INFO'}, f"{object.name} has no HD2 Swap ID. Skipping Swap.")
        global Global_BoneNames
        model = GetObjectsMeshData(Global_TocManager, Global_BoneNames)
        BlenderOpts = bpy.context.scene.Hd2ToolPanelSettings.get_settings_dict()
        Entry = Global_TocManager.GetEntryByLoadArchive(int(ID), MeshID)
        if Entry is None:
            self.report({'ERROR'},
                f"Archive for entry being saved is not loaded. Could not find custom property object at ID: {ID}")
            return{'CANCELLED'}
        if not Entry.IsLoaded: Entry.Load(True, False)
        m = model[ID]
        meshes = model[ID]
        for mesh_index, mesh in meshes.items():
            try:
                Entry.LoadedData.RawMeshes[mesh_index] = mesh
            except IndexError:
                excpectedLength = len(Entry.LoadedData.RawMeshes) - 1
                self.report({'ERROR'}, f"MeshInfoIndex of {mesh_index} for {object.name} exceeds the number of meshes. Expected maximum MeshInfoIndex is: {excpectedLength}. Please change the custom properties to match this value and resave the mesh.")
                return{'CANCELLED'}
        for mesh_index, mesh in meshes.items():
            try:
                if Entry.LoadedData.RawMeshes[mesh_index].DEV_BoneInfoIndex == -1 and object[
                    'BoneInfoIndex'] > -1:
                    self.report({'ERROR'},
                                f"Attempting to overwrite static mesh with {object[0].name}"
                                f", which has bones. Check your MeshInfoIndex is correct.")
                    return{'CANCELLED'}
                Entry.LoadedData.RawMeshes[mesh_index] = mesh
            except IndexError:
                self.report({'ERROR'},
                            f"MeshInfoIndex for {object[0].name} exceeds the number of meshes")
                return{'CANCELLED'}
        wasSaved = Entry.Save(BlenderOpts=BlenderOpts)
        if wasSaved:
            if not Global_TocManager.IsInPatch(Entry):
                Entry = Global_TocManager.AddEntryToPatch(int(ID), MeshID)
        else:
            self.report({"ERROR"}, f"Failed to save mesh {bpy.context.selected_objects[0].name}.")
            return{'CANCELLED'}
        self.report({'INFO'}, f"Saved Mesh Object ID: {self.object_id}")
        if SwapID != "" and SwapID.isnumeric():
                self.report({'INFO'}, f"Swapping Entry ID: {Entry.FileID} to: {SwapID}")
                Global_TocManager.RemoveEntryFromPatch(int(SwapID), MeshID)
                Entry.FileID = int(SwapID)
        return{'FINISHED'}

class BatchSaveStingrayMeshOperator(Operator):
    bl_label  = "Save Meshes"
    bl_idname = "helldiver2.archive_mesh_batchsave"
    bl_description = "Saves Meshes"
    bl_options = {'REGISTER', 'UNDO'} 

    def execute(self, context):
        start = time.time()
        errors = False
        if MeshNotValidToSave(self):
            return {'CANCELLED'}

        o = bpy.context.selected_objects

        if len(o) == 0:
            self.report({'WARNING'}, "No Objects Selected")
            return {'CANCELLED'}

        IDs = []
        IDswaps = {}
        objects = []
        for object in o:
            if object.type == 'MESH':
                objects.append(object)
        for i, object in enumerate(objects):
            SwapID = ""
            try:
                ID = object["Z_ObjectID"]
                try:
                    SwapID = object["Z_SwapID"]
                    IDswaps[SwapID] = ID
                    PrettyPrint(f"Found Swap of ID: {ID} Swap: {SwapID}")
                    if SwapID != "" and not SwapID.isnumeric():
                        self.report({"ERROR"}, f"Object: {object.name} has an incorrect Swap ID. Assure that the ID is a proper integer entry ID.")
                        return {'CANCELLED'}
                except:
                    self.report({'INFO'}, f"{object.name} has no HD2 Swap ID. Skipping Swap.")
                IDitem = [ID, SwapID]
                if IDitem not in IDs:
                    IDs.append(IDitem)
            except KeyError:
                self.report({'ERROR'}, f"{object.name} has no HD2 custom properties")
                return {'CANCELLED'}
        num_initially_selected = len(objects)
        swapCheck = {}
        for IDitem in IDs:
            ID = IDitem[0]
            SwapID = IDitem[1]
            if swapCheck.get(ID) == None:
                swapCheck[ID] = SwapID
            else:
                if (swapCheck[ID] == "" and SwapID != "") or (swapCheck[ID] != "" and SwapID == ""):
                    self.report({'ERROR'}, f"All Lods of object: {object.name} must have a swap ID! If you want to have an entry save to itself whilst swapping, set the SwapID to its own ObjectID.")
                    return {'CANCELLED'}
        objects_by_id = {}
        for obj in objects:
            try:
                objects_by_id[obj["Z_ObjectID"]][obj["MeshInfoIndex"]] = obj
            except KeyError:
                objects_by_id[obj["Z_ObjectID"]] = {obj["MeshInfoIndex"]: obj}
        global Global_BoneNames
        BlenderOpts = bpy.context.scene.Hd2ToolPanelSettings.get_settings_dict()
        num_meshes = len(objects)
        entries = []
        for IDitem in IDs:
            ID = IDitem[0]
            SwapID = IDitem[1]
            Entry = Global_TocManager.GetEntryByLoadArchive(int(ID), MeshID)
            if Entry is None:
                self.report({'ERROR'}, f"Archive for entry being saved is not loaded. Could not find custom property object at ID: {ID}")
                errors = True
                num_meshes -= len(MeshData[ID])
                entries.append(None)
                continue
            Entry.Load(True, False, True)
            if Global_TocManager.IsInPatch(Entry):
                Global_TocManager.RemoveEntryFromPatch(int(ID), MeshID)
            Entry = Global_TocManager.AddEntryToPatch(int(ID), MeshID)
            entries.append(Entry)
        MeshData = GetObjectsMeshData(Global_TocManager, Global_BoneNames)    
        for i, IDitem in enumerate(IDs):
            ID = IDitem[0]
            SwapID = IDitem[1]
            Entry = entries[i]
            if Entry is None:
                continue
            MeshList = MeshData[ID]
            for mesh_index, mesh in MeshList.items():
                try:
                    Entry.LoadedData.RawMeshes[mesh_index] = mesh
                except IndexError:
                    excpectedLength = len(Entry.LoadedData.RawMeshes) - 1
                    self.report({'ERROR'},f"MeshInfoIndex of {mesh_index} for {object.name} exceeds the number of meshes. Expected maximum MeshInfoIndex is: {excpectedLength}. Please change the custom properties to match this value and resave the mesh.")
                    errors = True
                    num_meshes -= 1
            wasSaved = Entry.Save(BlenderOpts=BlenderOpts)
            if wasSaved:
                if SwapID != "" and SwapID.isnumeric():
                    self.report({'INFO'}, f"Swapping Entry ID: {Entry.FileID} to: {SwapID}")
                    Global_TocManager.RemoveEntryFromPatch(int(SwapID), MeshID)
                    Entry.FileID = int(SwapID)
            else:
                self.report({"ERROR"}, f"Failed to save mesh with ID {ID}.")
                num_meshes -= len(MeshData[ID])
                continue
        PrettyPrint("Saving mesh materials")
        SaveMeshMaterials(objects)
        self.report({'INFO'}, f"Saved {num_meshes}/{num_initially_selected} selected Meshes")
        if errors:
            self.report({'ERROR'}, f"Errors occurred while saving meshes. Click here to view.")
        PrettyPrint(f"Time to save meshes: {time.time()-start}")
        return{'FINISHED'}

def SaveMeshMaterials(objects):
    if not bpy.context.scene.Hd2ToolPanelSettings.AutoSaveMeshMaterials:
        PrettyPrint(f"Skipping saving of materials as setting is disabled")
        return
    PrettyPrint(f"Saving materials for {len(objects)} objects")
    materials = []
    for object in objects:
        for slot in object.material_slots:
            if slot.material:
                materialName = slot.material.name
                PrettyPrint(f"Found material: {materialName} in {object.name}")
                try: 
                    material = bpy.data.materials[materialName]
                except:
                    raise Exception(f"Could not find material: {materialName}")
                if material not in materials:
                    materials.append(material)

    PrettyPrint(f"Found {len(materials)} unique materials {materials}")
    for material in materials:
        try:
            ID = int(material.name)
        except:
            PrettyPrint(f"Failed to convert material: {material.name} to ID")
            continue

        nodeName = ""
        for node in material.node_tree.nodes:
            if node.type == 'GROUP':
                nodeName = node.node_tree.name
                PrettyPrint(f"ID: {ID} Group: {nodeName}")
                break

        if nodeName == "" and not bpy.context.scene.Hd2ToolPanelSettings.SaveNonSDKMaterials:
            PrettyPrint(f"Cancelling Saving Material: {ID}")
            continue

        entry = Global_TocManager.GetEntry(ID, MaterialID)
        if entry:
            if not entry.IsModified:
                PrettyPrint(f"Saving material: {ID}")
                Global_TocManager.Save(ID, MaterialID)
            else:
                PrettyPrint(f"Skipping Saving Material: {ID} as it already has been modified")
        elif "-" in nodeName:
            if str(ID) in nodeName.split("-")[1]:
                template = nodeName.split("-")[0]
                PrettyPrint(f"Creating material: {ID} with template: {template}")
                CreateModdedMaterial(template, ID)
                Global_TocManager.Save(ID, MaterialID)
            else:
                PrettyPrint(f"Failed to find template from group: {nodeName}", "error")
        else:
            PrettyPrint(f"Failed to save material: {ID}", "error")


#endregion

#region Operators: Textures

# save texture from blender to archive button
# TODO: allow the user to choose an image, instead of looking for one of the same name
class SaveTextureFromBlendImageOperator(Operator):
    bl_label = "Save Texture"
    bl_idname = "helldiver2.texture_saveblendimage"
    bl_description = "Saves Texture"

    object_id: StringProperty()
    def execute(self, context):
        if PatchesNotLoaded(self):
            return {'CANCELLED'}
        Entries = EntriesFromString(self.object_id, TexID)
        for Entry in Entries:
            if Entry != None:
                if not Entry.IsLoaded: Entry.Load()
                try:
                    BlendImageToStingrayTexture(bpy.data.images[str(self.object_id)], Entry.LoadedData)
                except:
                    PrettyPrint("No blend texture was found for saving, using original", "warn"); pass
            Global_TocManager.Save(Entry.FileID, TexID)
        return{'FINISHED'}

# import texture from archive button
class ImportTextureOperator(Operator):
    bl_label = "Import Texture"
    bl_idname = "helldiver2.texture_import"
    bl_description = "Loads Texture into Blender Project"

    object_id: StringProperty()
    def execute(self, context):
        EntriesIDs = IDsFromString(self.object_id)
        for EntryID in EntriesIDs:
            Global_TocManager.Load(int(EntryID), TexID)
        return{'FINISHED'}

# export texture to file
class ExportTextureOperator(Operator, ExportHelper):
    bl_label = "Export Texture"
    bl_idname = "helldiver2.texture_export"
    bl_description = "Export Texture to a Desired File Location"
    filename_ext = ".dds"

    filter_glob: StringProperty(default='*.dds', options={'HIDDEN'})
    object_id: StringProperty(options={"HIDDEN"})
    def execute(self, context):
        Entry = Global_TocManager.GetEntry(int(self.object_id), TexID)
        if Entry != None:
            data = Entry.Load(False, False)
            with open(self.filepath, 'w+b') as f:
                f.write(Entry.LoadedData.ToDDS())
        return{'FINISHED'}
    
    def invoke(self, context, _event):
        if not self.filepath:
            blend_filepath = context.blend_data.filepath
            if not blend_filepath:
                blend_filepath = self.object_id
            else:
                blend_filepath = os.path.splitext(blend_filepath)[0]

            self.filepath = blend_filepath + self.filename_ext

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
class ExportTexturePNGOperator(Operator, ExportHelper):
    bl_label = "Export Texture"
    bl_idname = "helldiver2.texture_export_png"
    bl_description = "Export Texture to a Desired File Location"
    filename_ext = ".png"

    filter_glob: StringProperty(default='*.png', options={'HIDDEN'})
    object_id: StringProperty(options={"HIDDEN"})
    def execute(self, context):
        Global_TocManager.Load(int(self.object_id), TexID)
        Entry = Global_TocManager.GetEntry(int(self.object_id), TexID)
        if Entry != None:
            tempdir = tempfile.gettempdir()
            for i in range(Entry.LoadedData.ArraySize):
                filename = self.filepath.split(Global_backslash)[-1]
                directory = self.filepath.replace(filename, "")
                filename = filename.replace(".png", "")
                layer = "" if Entry.LoadedData.ArraySize == 1 else f"_layer{i}"
                dds_path = f"{tempdir}\\{filename}{layer}.dds"
                with open(dds_path, 'w+b') as f:
                    if Entry.LoadedData.ArraySize == 1:
                        f.write(Entry.LoadedData.ToDDS())
                    else:
                        f.write(Entry.LoadedData.ToDDSArray()[i])
                subprocess.run([Global_texconvpath, "-y", "-o", directory, "-ft", "png", "-f", "R8G8B8A8_UNORM", "-sepalpha", "-alpha", dds_path])
                if os.path.isfile(dds_path):
                    self.report({'INFO'}, f"Saved PNG Texture to: {dds_path}")
                else:
                    self.report({'ERROR'}, f"Failed to Save Texture: {dds_path}")
        return{'FINISHED'}
    
    def invoke(self, context, event):
        blend_filepath = context.blend_data.filepath
        filename = f"{self.object_id}.png"
        self.filepath = blend_filepath + filename
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# batch export texture to file
class BatchExportTextureOperator(Operator):
    bl_label = "Export Textures"
    bl_idname = "helldiver2.texture_batchexport"
    bl_description = "Export Textures to a Desired File Location"
    filename_ext = ".dds"

    directory: StringProperty(name="Outdir Path",description="dds output dir")
    filter_folder: BoolProperty(default=True,options={"HIDDEN"})

    object_id: StringProperty(options={"HIDDEN"})
    def execute(self, context):
        EntriesIDs = IDsFromString(self.object_id)
        for EntryID in EntriesIDs:
            Entry = Global_TocManager.GetEntry(EntryID, TexID)
            if Entry != None:
                data = Entry.Load(False, False)
                with open(self.directory + str(Entry.FileID)+".dds", 'w+b') as f:
                    f.write(Entry.LoadedData.ToDDS())
        return{'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
class BatchExportTexturePNGOperator(Operator):
    bl_label = "Export Texture"
    bl_idname = "helldiver2.texture_batchexport_png"
    bl_description = "Export Textures to a Desired File Location"
    filename_ext = ".png"

    directory: StringProperty(name="Outdir Path",description="png output dir")
    filter_folder: BoolProperty(default=True,options={"HIDDEN"})

    object_id: StringProperty(options={"HIDDEN"})
    def execute(self, context):
        EntriesIDs = IDsFromString(self.object_id)
        exportedfiles = 0
        for EntryID in EntriesIDs:
            Global_TocManager.Load(EntryID, TexID)
            Entry = Global_TocManager.GetEntry(EntryID, TexID)
            if Entry != None:
                tempdir = tempfile.gettempdir()
                dds_path = f"{tempdir}\\{EntryID}.dds"
                with open(dds_path, 'w+b') as f:
                    f.write(Entry.LoadedData.ToDDS())
                subprocess.run([Global_texconvpath, "-y", "-o", self.directory, "-ft", "png", "-f", "R8G8B8A8_UNORM", "-alpha", dds_path])
                filepath = f"{self.directory}\\{EntryID}.png"
                if os.path.isfile(filepath):
                    exportedfiles += 1
                else:
                    self.report({'ERROR'}, f"Failed to save texture as PNG: {filepath}")
        self.report({'INFO'}, f"Exported {exportedfiles} PNG Files To: {self.directory}")
        return{'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
# import texture from archive button
class SaveTextureFromDDSOperator(Operator, ImportHelper):
    bl_label = "Import DDS"
    bl_idname = "helldiver2.texture_savefromdds"
    bl_description = "Override Current Texture with a Selected DDS File"

    filter_glob: StringProperty(default='*.dds', options={'HIDDEN'})
    object_id: StringProperty(options={"HIDDEN"})
    def execute(self, context):
        if PatchesNotLoaded(self):
            return {'CANCELLED'}
        EntriesIDs = IDsFromString(self.object_id)
        for EntryID in EntriesIDs:
            SaveImageDDS(self.filepath, EntryID)
        
        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()

        return{'FINISHED'}


class SaveTextureFromPNGOperator(Operator, ImportHelper):
    bl_label = "Import PNG"
    bl_idname = "helldiver2.texture_savefrompng"
    bl_description = "Override Current Texture with a Selected PNG File"

    filter_glob: StringProperty(default='*.png', options={'HIDDEN'})
    object_id: StringProperty(options={"HIDDEN"})
    def execute(self, context):
        if PatchesNotLoaded(self):
            return {'CANCELLED'}
        EntriesIDs = IDsFromString(self.object_id)
        for EntryID in EntriesIDs:
            SaveImagePNG(self.filepath, EntryID)
        
        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()

        return{'FINISHED'}

def SaveImagePNG(filepath, object_id):
    Entry = Global_TocManager.GetEntry(int(object_id), TexID)
    if Entry != None:
        if len(filepath) > 1:
            # get texture data
            Entry.Load()
            StingrayTex = Entry.LoadedData
            tempdir = tempfile.gettempdir()
            PrettyPrint(filepath)
            PrettyPrint(StingrayTex.Format)
            subprocess.run([Global_texconvpath, "-y", "-o", tempdir, "-ft", "dds", "-dx10", "-f", StingrayTex.Format, "-sepalpha", "-alpha", filepath], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            nameIndex = filepath.rfind("\.".strip(".")) + 1
            fileName = filepath[nameIndex:].replace(".png", ".dds")
            dds_path = f"{tempdir}\\{fileName}"
            PrettyPrint(dds_path)
            if not os.path.exists(dds_path):
                raise Exception(f"Failed to convert to dds texture for: {dds_path}")
            with open(dds_path, 'r+b') as f:
                StingrayTex.FromDDS(f.read())
            Toc = MemoryStream(IOMode="write")
            Gpu = MemoryStream(IOMode="write")
            Stream = MemoryStream(IOMode="write")
            StingrayTex.Serialize(Toc, Gpu, Stream)
            # add texture to entry
            Entry.SetData(Toc.Data, Gpu.Data, Stream.Data, False)

            Global_TocManager.Save(int(object_id), TexID)

def SaveImageDDS(filepath, object_id):
    Entry = Global_TocManager.GetEntry(int(object_id), TexID)
    if Entry != None:
        if len(filepath) > 1:
            PrettyPrint(f"Saving image DDS: {filepath} to ID: {object_id}")
            # get texture data
            Entry.Load()
            StingrayTex = Entry.LoadedData
            with open(filepath, 'r+b') as f:
                StingrayTex.FromDDS(f.read())
            Toc = MemoryStream(IOMode="write")
            Gpu = MemoryStream(IOMode="write")
            Stream = MemoryStream(IOMode="write")
            StingrayTex.Serialize(Toc, Gpu, Stream)
            # add texture to entry
            Entry.SetData(Toc.Data, Gpu.Data, Stream.Data, False)

            Global_TocManager.Save(int(object_id), TexID)
#endregion

#region Operators: Materials

class SaveMaterialOperator(Operator):
    bl_label = "Save Material"
    bl_idname = "helldiver2.material_save"
    bl_description = "Saves Material"

    object_id: StringProperty()
    def execute(self, context):
        if PatchesNotLoaded(self):
            return {'CANCELLED'}
        EntriesIDs = IDsFromString(self.object_id)
        for EntryID in EntriesIDs:
            Global_TocManager.Save(int(EntryID), MaterialID)
        return{'FINISHED'}

class ImportMaterialOperator(Operator):
    bl_label = "Import Material"
    bl_idname = "helldiver2.material_import"
    bl_description = "Loads Materials into Blender Project"

    object_id: StringProperty()
    def execute(self, context):
        EntriesIDs = IDsFromString(self.object_id)
        for EntryID in EntriesIDs:
            Global_TocManager.Load(int(EntryID), MaterialID)
        return{'FINISHED'}

class AddMaterialOperator(Operator):
    bl_label = "Add Material"
    bl_idname = "helldiver2.material_add"
    bl_description = "Adds a New Material to Current Active Patch"

    global Global_Materials
    selected_material: EnumProperty(items=Global_Materials, name="Template", default=0)

    def execute(self, context):
        if PatchesNotLoaded(self):
            return {'CANCELLED'}
        
        CreateModdedMaterial(self.selected_material)

        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()
        LoadEntryLists()
        
        return{'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
class SetMaterialTemplateOperator(Operator):
    bl_label = "Set Template"
    bl_idname = "helldiver2.material_set_template"
    bl_description = "Sets the material to a modded material template"
    
    global Global_Materials
    selected_material: EnumProperty(items=Global_Materials, name="Template", default=0)

    entry_id: StringProperty()

    def execute(self, context):
        if PatchesNotLoaded(self):
            return {'CANCELLED'}
        
        PrettyPrint(f"Found: {self.entry_id}")
            
        Entry = Global_TocManager.GetEntry(int(self.entry_id), MaterialID)
        if not Entry:
            raise Exception(f"Could not find entry at ID: {self.entry_id}")

        Entry.MaterialTemplate = self.selected_material
        Entry.Load(True)
        
        PrettyPrint(f"Finished Set Template: {self.selected_material}")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

def CreateModdedMaterial(template, ID=None):
    path = f"{Global_materialpath}\\{template}.material"
    if not os.path.exists(path):
        raise Exception(f"Selected material template: {template} does not exist")

    Entry = TocEntry()
    if ID == None:
        Entry.FileID = RandomHash16()
        PrettyPrint(f"File ID is now: {Entry.FileID}")
    else:
        Entry.FileID = ID
        PrettyPrint(f"Found pre-existing file ID: {ID}")

    Entry.TypeID = MaterialID
    Entry.MaterialTemplate = template
    Entry.IsCreated = True
    with open(path, 'r+b') as f:
        data = f.read()
    Entry.TocData_OLD   = data
    Entry.TocData       = data

    Global_TocManager.AddNewEntryToPatch(Entry)
        
    EntriesIDs = IDsFromString(str(Entry.FileID))
    for EntryID in EntriesIDs:
        Global_TocManager.Load(int(EntryID), MaterialID)

class ShowMaterialEditorOperator(Operator):
    bl_label = "Show Material Editor"
    bl_idname = "helldiver2.material_showeditor"
    bl_description = "Show List of Textures in Material"

    object_id: StringProperty()
    def execute(self, context):
        Entry = Global_TocManager.GetEntry(int(self.object_id), MaterialID)
        if Entry != None:
            if not Entry.IsLoaded: Entry.Load(False, False)
            mat = Entry.LoadedData
            if mat.DEV_ShowEditor:
                mat.DEV_ShowEditor = False
            else:
                mat.DEV_ShowEditor = True
        return{'FINISHED'}

class SetMaterialTexture(Operator, ImportHelper):
    bl_label = "Set Material Texture"
    bl_idname = "helldiver2.material_settex"

    filename_ext = ".dds"

    filter_glob: StringProperty(default="*.dds", options={'HIDDEN'})

    object_id: StringProperty(options={"HIDDEN"})
    tex_idx: IntProperty(options={"HIDDEN"})

    def execute(self, context):
        Entry = Global_TocManager.GetEntry(int(self.object_id), MaterialID)
        if Entry != None:
            if Entry.IsLoaded:
                Entry.LoadedData.DEV_DDSPaths[self.tex_idx] = self.filepath
        
        # Redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()
        
        return{'FINISHED'}

#endregion

#region Operators : Animation
class ImportStingrayAnimationOperator(Operator):
    bl_label = "Import Animation"
    bl_idname = "helldiver2.archive_animation_import"
    bl_description = "Loads Animation into Blender Scene"
    
    object_id: StringProperty()
    def execute(self, context):
        # check if armature selected
        armature = context.active_object
        if armature.type != "ARMATURE":
            self.report({'ERROR'}, "Please select an armature to import the animation to")
            return {'CANCELLED'}
        animation_id = self.object_id
        try:
            Global_TocManager.Load(int(animation_id), AnimationID)
        except AnimationException as e:
            self.report({'ERROR'}, f"{e}")
            return {'CANCELLED'}
        except Exception as error:
            PrettyPrint(f"Encountered unknown animation error: {error}", 'error')
            self.report({'ERROR'}, f"Encountered an error whilst importing animation. See Console for more info.")
            return {'CANCELLED'}
        return{'FINISHED'}
        
class SaveStingrayAnimationOperator(Operator):
    bl_label  = "Save Animation"
    bl_idname = "helldiver2.archive_animation_save"
    bl_description = "Saves animation"
    
    def execute(self, context):
        if PatchesNotLoaded(self):
            return{'CANCELLED'}
        object = bpy.context.active_object
        if object.animation_data is None or object.animation_data.action is None:
            self.report({'ERROR'}, "Armature has no active action!")
            return {'CANCELLED'}
        if object == None or object.type != "ARMATURE":
            self.report({'ERROR'}, "Please select an armature")
            return {'CANCELLED'}
        action_name = object.animation_data.action.name
        if len(object.animation_data.action.fcurves) == 0:
            self.report({'ERROR'}, f"Action: {action_name} has no keyframe data! Make sure your animation has at least an initial keyframe with a recorded pose.")
            return {'CANCELLED'}
        entry_id = action_name.split(" ")[0].split("_")[0].split(".")[0]
        if entry_id.startswith("0x"):
            entry_id = hex_to_decimal(entry_id)
        try:
            bones_id = object['BonesID']
        except Exception as e:
            PrettyPrint(f"Encountered animation error: {e}", 'error')
            self.report({'ERROR'}, f"Armature: {object.name} is missing HD2 custom property: BonesID")
            return{'CANCELLED'}
        PrettyPrint(f"Getting Animation Entry: {entry_id}")
        animation_entry = Global_TocManager.GetEntryByLoadArchive(int(entry_id), AnimationID)
        if not animation_entry:
            self.report({'ERROR'}, f"Could not find animation entry for Action: {action_name} as EntryID: {entry_id}. Assure your action name starts with a valid ID for the animation entry.")
            return{'CANCELLED'}
        if not animation_entry.IsLoaded: animation_entry.Load(True, False)
        bones_entry = Global_TocManager.GetEntryByLoadArchive(int(bones_id), BoneID)
        bones_data = bones_entry.TocData
        try:
            animation_entry.LoadedData.load_from_armature(context, object, bones_data)
        except AnimationException as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        wasSaved = animation_entry.Save()
        if wasSaved:
            if not Global_TocManager.IsInPatch(animation_entry):
                animation_entry = Global_TocManager.AddEntryToPatch(int(entry_id), AnimationID)
            else:
                Global_TocManager.RemoveEntryFromPatch(int(entry_id), AnimationID)
                animation_entry = Global_TocManager.AddEntryToPatch(int(entry_id), AnimationID)
        else:
            self.report({"ERROR"}, f"Failed to save animation for armature {bpy.context.selected_objects[0].name}.")
            return{'CANCELLED'}
        self.report({'INFO'}, f"Saved Animation")
        return {'FINISHED'}

#region Operators: Particles
class SaveStingrayParticleOperator(Operator):
    bl_label  = "Save Particle"
    bl_idname = "helldiver2.particle_save"
    bl_description = "Saves Particle"
    bl_options = {'REGISTER', 'UNDO'} 

    object_id: StringProperty()
    def execute(self, context):
        mode = context.mode
        if mode != 'OBJECT':
            self.report({'ERROR'}, f"You are Not in OBJECT Mode. Current Mode: {mode}")
            return {'CANCELLED'}
        wasSaved = Global_TocManager.Save(int(self.object_id), ParticleID)

        # we can handle below later when we put a particle object into the blender scene

        # if not wasSaved:
        #         for object in bpy.data.objects:
        #             try:
        #                 ID = object["Z_ObjectID"]
        #                 self.report({'ERROR'}, f"Archive for entry being saved is not loaded. Object: {object.name} ID: {ID}")
        #                 return{'CANCELLED'}
        #             except:
        #                 self.report({'ERROR'}, f"Failed to find object with custom property ID. Object: {object.name}")
        #                 return{'CANCELLED'}
        # self.report({'INFO'}, f"Saved Mesh Object ID: {self.object_id}")
        return{'FINISHED'}
class ImportStingrayParticleOperator(Operator):
    bl_label = "Import Particle"
    bl_idname = "helldiver2.archive_particle_import"
    bl_description = "Loads Particles into Blender Scene"

    object_id: StringProperty()
    def execute(self, context):
        EntriesIDs = IDsFromString(self.object_id)
        Errors = []
        for EntryID in EntriesIDs:
            if len(EntriesIDs) == 1:
                Global_TocManager.Load(EntryID, ParticleID)
            else:
                try:
                    Global_TocManager.Load(EntryID, ParticleID)
                except Exception as error:
                    Errors.append([EntryID, error])

        if len(Errors) > 0:
            PrettyPrint("\nThese errors occurred while attempting to load particles...", "error")
            idx = 0
            for error in Errors:
                PrettyPrint(f"  Error {idx}: for particle {error[0]}", "error")
                PrettyPrint(f"    {error[1]}\n", "error")
                idx += 1
            raise Exception("One or more particles failed to load")
        return{'FINISHED'}
#endregion

#region Operators: Clipboard Functionality

class CopyArchiveEntryOperator(Operator):
    bl_label = "Copy Entry"
    bl_idname = "helldiver2.archive_copy"
    bl_description = "Copy Selected Entries"

    object_id: StringProperty()
    object_typeid: StringProperty()
    def execute(self, context):
        Entries = EntriesFromStrings(self.object_id, self.object_typeid)
        Global_TocManager.Copy(Entries)
        return{'FINISHED'}

class PasteArchiveEntryOperator(Operator):
    bl_label = "Paste Entry"
    bl_idname = "helldiver2.archive_paste"
    bl_description = "Paste Selected Entries"

    def execute(self, context):
        Global_TocManager.Paste()
        return{'FINISHED'}

class ClearClipboardOperator(Operator):
    bl_label = "Clear Clipboard"
    bl_idname = "helldiver2.archive_clearclipboard"
    bl_description = "Clear Selected Entries from Clipboard"

    def execute(self, context):
        Global_TocManager.ClearClipboard()
        return{'FINISHED'}

class CopyTextOperator(Operator):
    bl_label  = "Copy ID"
    bl_idname = "helldiver2.copytest"
    bl_description = "Copies Entry Information"

    text: StringProperty()
    def execute(self, context):
        cmd='echo|set /p="'+str(self.text).strip()+'"|clip'
        subprocess.check_call(cmd, shell=True)
        self.report({'INFO'}, f"Copied: {self.text}")
        return{'FINISHED'}

#endregion

#region Operators: UI/UX

class LoadArchivesOperator(Operator):
    bl_label = "Load Archives"
    bl_idname = "helldiver2.archives_import"
    bl_description = "Loads Selected Archive"

    paths_str: StringProperty(name="paths_str")
    def execute(self, context):
        global Global_TocManager
        if self.paths_str != "" and os.path.exists(self.paths_str):
            Global_TocManager.LoadArchive(self.paths_str)
            id = self.paths_str.replace(Global_gamepath, "")
            name = f"{GetArchiveNameFromID(id)} {id}"
            self.report({'INFO'}, f"Loaded {name}")
            return{'FINISHED'}
        else:
            message = "Archive Failed to Load"
            if not os.path.exists(self.paths_str):
                message = "Current Filepath is Invalid. Change This in Settings"
            self.report({'ERROR'}, message )
            return{'CANCELLED'}

class SearchArchivesOperator(Operator):
    bl_label = "Search Found Archives"
    bl_idname = "helldiver2.search_archives"
    bl_description = "Search from Found Archives"

    SearchField : StringProperty(name="SearchField", default="")
    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, "SearchField", icon='VIEWZOOM')
        # Update displayed archives
        if self.PrevSearch != self.SearchField:
            self.PrevSearch = self.SearchField

            self.ArchivesToDisplay = []
            for Entry in Global_ArchiveHashes:
                if Entry[1].lower().find(self.SearchField.lower()) != -1:
                    self.ArchivesToDisplay.append([Entry[0], Entry[1]])
    
        if self.SearchField != "" and len(self.ArchivesToDisplay) == 0:
            row = layout.row(); row.label(text="No Archive IDs Found")
            row = layout.row(); row.label(text="Know an ID that's Not Here?")
            row = layout.row(); row.label(text="Make an issue on the github.")
            row = layout.row(); row.label(text="Archive ID and In Game Name")
            row = layout.row(); row.operator("helldiver2.github", icon= 'URL')

        else:
            for Archive in self.ArchivesToDisplay:
                row = layout.row()
                row.label(text=Archive[1], icon='GROUP')
                row.operator("helldiver2.archives_import", icon= 'FILE_NEW', text="").paths_str = Global_gamepath + str(Archive[0])

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        self.PrevSearch = "NONE"
        self.ArchivesToDisplay = []

        wm = context.window_manager
        return wm.invoke_props_dialog(self)

class SelectAllOfTypeOperator(Operator):
    bl_label  = "Select All"
    bl_idname = "helldiver2.select_type"
    bl_description = "Selects All of Type in Section"

    object_typeid: StringProperty()
    def execute(self, context):
        Entries = GetDisplayData()[0]
        for EntryInfo in Entries:
            Entry = EntryInfo[0]
            if Entry.TypeID == int(self.object_typeid):
                DisplayEntry = Global_TocManager.GetEntry(Entry.FileID, Entry.TypeID)
                if DisplayEntry.IsSelected:
                    #Global_TocManager.DeselectEntries([Entry])
                    pass
                else:
                    Global_TocManager.SelectEntries([Entry], True)
        return{'FINISHED'}
    
class ImportAllOfTypeOperator(Operator):
    bl_label  = "Import All Of Type"
    bl_idname = "helldiver2.import_type"

    object_typeid: StringProperty()
    def execute(self, context):
        Entries = GetDisplayData()[0]
        for EntryInfo in Entries:
            Entry = EntryInfo[0]
            #if Entry.TypeID == int(self.object_typeid):
            DisplayEntry = Global_TocManager.GetEntry(Entry.FileID, Entry.TypeID)
            objectid = str(DisplayEntry.FileID)

            if DisplayEntry.TypeID == MeshID or DisplayEntry.TypeID == CompositeMeshID:
                EntriesIDs = IDsFromString(objectid)
                for EntryID in EntriesIDs:
                    try:
                        Global_TocManager.Load(EntryID, MeshID)
                    except Exception as error:
                        self.report({'ERROR'},[EntryID, error])

            elif DisplayEntry.TypeID == TexID:
                print("tex")
                #operator = bpy.ops.helldiver2.texture_import(object_id=objectid)
                #ImportTextureOperator.execute(operator, operator)

            elif DisplayEntry.TypeID == MaterialID:
                print("mat")
                #operator = bpy.ops.helldiver2.material_import(object_id=objectid)
                #ImportMaterialOperator.execute(operator, operator)
        return{'FINISHED'}

class SetEntryFriendlyNameOperator(Operator):
    bl_label = "Set Friendly Name"
    bl_idname = "helldiver2.archive_setfriendlyname"
    bl_description = "Change Entry Display Name"

    NewFriendlyName : StringProperty(name="NewFriendlyName", default="")
    def draw(self, context):
        layout = self.layout; row = layout.row()
        row.prop(self, "NewFriendlyName", icon='COPY_ID')
        row = layout.row()
        if murmur64_hash(str(self.NewFriendlyName).encode()) == int(self.object_id):
            row.label(text="Hash is correct")
        else:
            row.label(text="Hash is incorrect")
        row.label(text=str(murmur64_hash(str(self.NewFriendlyName).encode())))

    object_id: StringProperty()
    def execute(self, context):
        AddFriendlyName(int(self.object_id), str(self.NewFriendlyName))
        return{'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

#endregion

#region Operators: Help

class HelpOperator(Operator):
    bl_label  = "Help"
    bl_idname = "helldiver2.help"
    bl_description = "Link to Modding Discord"

    def execute(self, context):
        url = "https://discord.gg/helldiversmodding"
        webbrowser.open(url, new=0, autoraise=True)
        return{'FINISHED'}

class ArchiveSpreadsheetOperator(Operator):
    bl_label  = "Archive Spreadsheet"
    bl_idname = "helldiver2.archive_spreadsheet"
    bl_description = "Opens Spreadsheet with Indentified Archives"

    def execute(self, context):
        url = "https://docs.google.com/spreadsheets/d/1oQys_OI5DWou4GeRE3mW56j7BIi4M7KftBIPAl1ULFw"
        webbrowser.open(url, new=0, autoraise=True)
        return{'FINISHED'}

class GithubOperator(Operator):
    bl_label  = "Github"
    bl_idname = "helldiver2.github"
    bl_description = "Opens The Github Page"

    def execute(self, context):
        url = "https://github.com/Boxofbiscuits97/HD2SDK-CommunityEdition"
        webbrowser.open(url, new=0, autoraise=True)
        return{'FINISHED'}
    
class LatestReleaseOperator(Operator):
    bl_label  = "Update Helldivers 2 SDK"
    bl_idname = "helldiver2.latest_release"
    bl_description = "Opens The Github Page to the latest release"

    def execute(self, context):
        url = "https://github.com/Boxofbiscuits97/HD2SDK-CommunityEdition/releases/latest"
        webbrowser.open(url, new=0, autoraise=True)
        return{'FINISHED'}

class MeshFixOperator(Operator, ImportHelper):
    bl_label = "Fix Meshes"
    bl_idname = "helldiver2.meshfixtool"
    bl_description = "Auto-fixes meshes in the currently loaded patch. Warning, this may take some time."

    directory: StringProperty(
        name="Directory",
        description="Choose a directory",
        subtype='DIR_PATH'
    )
    
    filter_folder: BoolProperty(
        default=True,
        options={'HIDDEN'}
    )
    
    use_filter_folder = True
    def execute(self, context):   
        if ArchivesNotLoaded(self):
            return {'CANCELLED'}
        path = self.directory
        output = RepatchMeshes(self, path)
        if output == {'CANCELLED'}: return {'CANCELLED'}
        
        return{'FINISHED'}
#endregion

def RepatchMeshes(self, path):
    if len(bpy.context.scene.objects) > 0:
        self.report({'ERROR'}, f"Scene is not empty! Please remove all objects in the scene before starting the repatching process!")
        return{'CANCELLED'}
    
    Global_TocManager.UnloadPatches()
    
    settings = bpy.context.scene.Hd2ToolPanelSettings
    settings.ImportLods = False
    settings.AutoLods = True
    settings.ImportStatic = False
    
    PrettyPrint(f"Searching for patch files in: {path}")
    patchPaths = []
    LoopPatchPaths(patchPaths, path)
    PrettyPrint(f"Found Patch Paths: {patchPaths}")
    if len(patchPaths) == 0:
        self.report({'ERROR'}, f"No patch files were found in selected path")
        return{'ERROR'}

    errors = []
    for path in patchPaths:
        PrettyPrint(f"Patching: {path}")
        Global_TocManager.LoadArchive(path, True, True)
        numMeshesRepatched = 0
        failed = False
        for entry in Global_TocManager.ActivePatch.TocEntries:
            if entry.TypeID != MeshID:
                PrettyPrint(f"Skipping {entry.FileID} as it is not a mesh entry")
                continue
            PrettyPrint(f"Repatching {entry.FileID}")
            Global_TocManager.GetEntryByLoadArchive(entry.FileID, entry.TypeID)
            settings.AutoLods = True
            settings.ImportStatic = False
            numMeshesRepatched += 1
            entry.Load(False, True)
            patchObjects = bpy.context.scene.objects
            if len(patchObjects) == 0: # Handle static meshes
                settings.AutoLods = False
                settings.ImportStatic = True
                entry.Load(False, True)
                patchObjects = bpy.context.scene.objects
            OldMeshInfoIndex = patchObjects[0]['MeshInfoIndex']
            fileID = entry.FileID
            typeID = entry.TypeID
            Global_TocManager.RemoveEntryFromPatch(fileID, typeID)
            Global_TocManager.AddEntryToPatch(fileID, typeID)
            newEntry = Global_TocManager.GetEntry(fileID, typeID)
            if newEntry:
                PrettyPrint(f"Entry successfully created")
            else:
                failed = True
                errors.append([path, fileID, "Could not create newEntry", "error"])
                continue
            newEntry.Load(False, False)
            NewMeshes = newEntry.LoadedData.RawMeshes
            NewMeshInfoIndex = ""
            for mesh in NewMeshes:
                if mesh.LodIndex == 0:
                    NewMeshInfoIndex = mesh.MeshInfoIndex
            if NewMeshInfoIndex == "": # if the index is still a string, we couldn't find it
                PrettyPrint(f"Could not find LOD 0 for mesh: {fileID}. Skipping mesh index checks", "warn")
                errors.append([path, fileID, "Could not find LOD 0 for mesh so LOD index updates did not occur. This may be intended", "warn"])
            else:
                PrettyPrint(f"Old MeshIndex: {OldMeshInfoIndex} New MeshIndex: {NewMeshInfoIndex}")
                if OldMeshInfoIndex != NewMeshInfoIndex:
                    PrettyPrint(f"Swapping mesh index to new index", "warn")
                    patchObjects[0]['MeshInfoIndex'] = NewMeshInfoIndex
            for object in patchObjects:
                object.select_set(True)
            newEntry.Save()
            for object in bpy.context.scene.objects:
                bpy.data.objects.remove(object)

        if not failed:
            Global_TocManager.PatchActiveArchive()
            PrettyPrint(f"Repatched {numMeshesRepatched} meshes in patch: {path}")
        else:
            PrettyPrint(f"Faield to repatch meshes in patch: {path}", "error")
        Global_TocManager.UnloadPatches()
    
    if len(errors) == 0:
        PrettyPrint(f"Finished repatching {len(patchPaths)} modsets")
        self.report({'INFO'}, f"Finished Repatching meshes with no errors")
    else:
        for error in errors:
            PrettyPrint(f"Failed to patch mesh: {error[1]} in patch: {error[0]} Error: {error[2]}", error[3])
        self.report({'ERROR'}, f"Failed to patch {len(errors)} meshes. Please check logs to see the errors")

def LoopPatchPaths(list, filepath):
    for path in os.listdir(filepath):
        path = f"{filepath}/{path}"
        if Path(path).is_dir():
            PrettyPrint(f"Looking in folder: {path}")
            LoopPatchPaths(list, path)
            continue
        if "patch_" in path:
            PrettyPrint(f"Adding Path: {path}")
            strippedpath = path.replace(".gpu_resources", "").replace(".stream", "")
            if strippedpath not in list:
                list.append(strippedpath)
        else:
            PrettyPrint(f"Path: {path} is not a patch file. Ignoring file.", "warn")
            
#region Operators: Context Menu

stored_custom_properties = {}
class CopyCustomPropertyOperator(Operator):
    bl_label = "Copy HD2 Properties"
    bl_idname = "helldiver2.copy_custom_properties"
    bl_description = "Copies Custom Property Data for Helldivers 2 Objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global stored_custom_properties
        
        selectedObjects = context.selected_objects
        if len(selectedObjects) == 0:
            self.report({'WARNING'}, "No active object selected")
            return {'CANCELLED'}
        PrettyPrint(selectedObjects)

        obj = context.active_object
        stored_custom_properties.clear()
        for key, value in obj.items():
            if key not in obj.bl_rna.properties:  # Skip built-in properties
                stored_custom_properties[key] = value

        self.report({'INFO'}, f"Copied {len(stored_custom_properties)} custom properties")
        return {'FINISHED'}

class PasteCustomPropertyOperator(Operator):
    bl_label = "Paste HD2 Properties"
    bl_idname = "helldiver2.paste_custom_properties"
    bl_description = "Pastes Custom Property Data for Helldivers 2 Objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global stored_custom_properties

        selectedObjects = context.selected_objects
        if len(selectedObjects) == 0:
            self.report({'WARNING'}, "No active object selected")
            return {'CANCELLED'}

        obj = context.active_object
        if not stored_custom_properties:
            self.report({'WARNING'}, "No custom properties to paste")
            return {'CANCELLED'}

        for key, value in stored_custom_properties.items():
            obj[key] = value

        for area in bpy.context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Pasted {len(stored_custom_properties)} custom properties")
        return {'FINISHED'}

def CustomPropertyContext(self, context):
    layout = self.layout
    layout.separator()
    layout.label(text=Global_SectionHeader)
    layout.separator()
    layout.operator("helldiver2.copy_hex_id", icon='COPY_ID')
    layout.operator("helldiver2.copy_decimal_id", icon='COPY_ID')
    layout.separator()
    layout.operator("helldiver2.copy_custom_properties", icon= 'COPYDOWN')
    layout.operator("helldiver2.paste_custom_properties", icon= 'PASTEDOWN')
    layout.separator()
    layout.operator("helldiver2.archive_animation_save", icon='ARMATURE_DATA')
    layout.operator("helldiver2.archive_mesh_batchsave", icon= 'FILE_BLEND')

class CopyArchiveIDOperator(Operator):
    bl_label = "Copy Archive ID"
    bl_idname = "helldiver2.copy_archive_id"
    bl_description = "Copies the Active Archive's ID to Clipboard"

    def execute(self, context):
        if ArchivesNotLoaded(self):
            return {'CANCELLED'}
        archiveID = str(Global_TocManager.ActiveArchive.Name)
        bpy.context.window_manager.clipboard = archiveID
        self.report({'INFO'}, f"Copied Archive ID: {archiveID}")

        return {'FINISHED'}
    
class CopyHexIDOperator(Operator):
    bl_label = "Copy Hex ID"
    bl_idname = "helldiver2.copy_hex_id"
    bl_description = "Copy the Hexidecimal ID of the selected mesh for the Diver tool"

    def execute(self, context):
        object = context.active_object
        if not object:
            self.report({"ERROR"}, "No object is selected")
        try:
            ID = int(object["Z_ObjectID"])
        except:
            self.report({'ERROR'}, f"Object: {object.name} has not Helldivers property ID")
            return {'CANCELLED'}

        try:
            hexID = hex(ID)
        except:
            self.report({'ERROR'}, f"Object: {object.name} ID: {ID} cannot be converted to hex")
            return {'CANCELLED'}
        
        CopyToClipboard(hexID)
        self.report({'INFO'}, f"Copied {object.name}'s property of {hexID}")
        return {'FINISHED'}

class CopyDecimalIDOperator(Operator):
    bl_label = "Copy ID"
    bl_idname = "helldiver2.copy_decimal_id"
    bl_description = "Copy the decimal ID of the selected mesh"

    def execute(self, context):
        object = context.active_object
        if not object:
            self.report({"ERROR"}, "No object is selected")
        try:
            ID = str(object["Z_ObjectID"])
        except:
            self.report({'ERROR'}, f"Object: {object.name} has not Helldivers property ID")
            return {'CANCELLED'}
        
        CopyToClipboard(ID)
        self.report({'INFO'}, f"Copied {object.name}'s property of {ID}")
        return {'FINISHED'}

class EntrySectionOperator(Operator):
    bl_label = "Collapse Section"
    bl_idname = "helldiver2.collapse_section"
    bl_description = "Fold Current Section"

    type: StringProperty(default = "")

    def execute(self, context):
        global Global_Foldouts
        for i in range(len(Global_Foldouts)):
            if Global_Foldouts[i][0] == str(self.type):
                Global_Foldouts[i][1] = not Global_Foldouts[i][1]
                PrettyPrint(f"Folding foldout: {Global_Foldouts[i]}")
        return {'FINISHED'}
#endregion

#region Menus and Panels

def LoadedArchives_callback(scene, context):
    return [(Archive.Name, GetArchiveNameFromID(Archive.Name) if GetArchiveNameFromID(Archive.Name) != "" else Archive.Name, Archive.Name) for Archive in Global_TocManager.LoadedArchives]

def Patches_callback(scene, context):
    return [(Archive.Name, Archive.Name, Archive.Name) for Archive in Global_TocManager.Patches]
    
def ChangeLoadedArchive(self, context):
    Global_TocManager.SetActiveByName(self.LoadedArchives)
    
def ChangeActivePatch(self, context):
    Global_TocManager.SetActivePatchByName(self.Patches)

class Hd2ToolPanelSettings(PropertyGroup):
    # Patches
    Patches   : EnumProperty(name="Patches", items=Patches_callback, update=ChangeActivePatch)
    PatchOnly : BoolProperty(name="Show Patch Entries Only", description = "Filter list to entries present in current patch", default = False)
    # Archive
    ContentsExpanded : BoolProperty(default = True)
    LoadedArchives   : EnumProperty(name="LoadedArchives", items=LoadedArchives_callback, update=ChangeLoadedArchive)
    # Settings
    MenuExpanded     : BoolProperty(default = False)

    ShowExtras       : BoolProperty(name="Extra Entry Types", description = "Shows all Extra entry types.", default = False)
    FriendlyNames    : BoolProperty(name="Show Friendly Names", description="Enable friendly names for entries if they have any. Disabling this option can greatly increase UI preformance if a patch has a large number of entries.", default = True)

    ImportMaterials  : BoolProperty(name="Import Materials", description = "Fully import materials by appending the textures utilized, otherwise create placeholders", default = True)
    ImportLods       : BoolProperty(name="Import LODs", description = "Import LODs", default = False)
    ImportGroup0     : BoolProperty(name="Import Group 0 Only", description = "Only import the first vertex group, ignore others", default = True)
    ImportCulling    : BoolProperty(name="Import Culling Bounds", description = "Import Culling Bodies", default = False)
    ImportStatic     : BoolProperty(name="Import Static Meshes", description = "Import Static Meshes", default = False)
    MakeCollections  : BoolProperty(name="Make Collections", description = "Make new collection when importing meshes", default = False)
    Force3UVs        : BoolProperty(name="Force 3 UV Sets", description = "Force at least 3 UV sets, some materials require this", default = True)
    Force1Group      : BoolProperty(name="Force 1 Group", description = "Force mesh to only have 1 vertex group", default = True)
    AutoLods         : BoolProperty(name="Auto LODs", description = "Automatically generate LOD entries based on LOD0, does not actually reduce the quality of the mesh", default = True)
    RemoveGoreMeshes : BoolProperty(name="Remove Gore Meshes", description = "Automatically delete all of the verticies with the gore material when loading a model", default = False)
    SaveBonePositions: BoolProperty(name="Save Bone Positions", description = "Include bone positions in animation (may mess with additive animations being applied)", default = False)
    ImportArmature   : BoolProperty(name="Import Armatures", description = "Import unit armature data", default = True)
    MergeArmatures   : BoolProperty(name="Merge Armatures", description = "Merge new armatures to the selected armature", default = True)
    ParentArmature   : BoolProperty(name="Parent Armatures", description = "Make imported armatures the parent of the imported mesh", default = True)
    # Search
    SearchField      : StringProperty(default = "")

    # Tools
    EnableTools           : BoolProperty(name="Special Tools", description = "Enable advanced SDK Tools", default = False)
    UnloadEmptyArchives   : BoolProperty(name="Unload Empty Archives", description="Unload Archives that do not Contain any Textures, Materials, or Meshes", default = True)
    DeleteOnLoadArchive   : BoolProperty(name="Nuke Files on Archive Load", description="Delete all Textures, Materials, and Meshes in project when selecting a new archive", default = False)
    UnloadPatches         : BoolProperty(name="Unload Previous Patches", description="Unload Previous Patches when bulk loading")
    LoadFoundArchives     : BoolProperty(name="Load Found Archives", description="Load the archives found when search by entry ID", default=True)

    AutoSaveMeshMaterials : BoolProperty(name="Autosave Mesh Materials", description="Save unsaved material entries applied to meshes when the mesh is saved", default = True)
    SaveNonSDKMaterials   : BoolProperty(name="Save Non-SDK Materials", description="Toggle if non-SDK materials should be autosaved when saving a mesh", default = False)
    SaveUnsavedOnWrite    : BoolProperty(name="Save Unsaved on Write", description="Save all entries that are unsaved when writing a patch", default = True)
    PatchBaseArchiveOnly  : BoolProperty(name="Patch Base Archive Only", description="When enabled, it will allow patched to only be created if the base archive is selected. This is helpful for new users.", default = True)
    LegacyWeightNames     : BoolProperty(name="Legacy Weight Names", description="Brings back the old naming system for vertex groups using the X_Y schema", default = False)
    
    SaveTexturesWithMaterial: BoolProperty(name="Save Textures with Material", description="Save a material\'s referenced textures to the patch when said material is saved. When disabled, new random IDs will not be given each time the material is saved", default = True)
    GenerateRandomTextureIDs: BoolProperty(name="Generate Random Texture IDs", description="Give a material\'s referenced textures new random IDs when said material is saved", default = True)

    def get_settings_dict(self):
        dict = {}
        dict["MenuExpanded"] = self.MenuExpanded
        dict["ShowExtras"] = self.ShowExtras
        dict["Force3UVs"] = self.Force3UVs
        dict["Force1Group"] = self.Force1Group
        dict["AutoLods"] = self.AutoLods
        return dict

def LoadEntryLists():
    archive = Global_TocManager.ActiveArchive
    patch = Global_TocManager.ActivePatch
    for t in Global_TypeIDs:
        getattr(bpy.context.scene, f"list_{t}").clear()
    if archive:
        for Entry in archive.TocEntries:
            try:
                l = getattr(bpy.context.scene, f"list_{Entry.TypeID}")
            except AttributeError:
                continue
            new_item = l.add()
            new_item.item_name = str(Entry.FileID)
            new_item.item_type = str(Entry.TypeID)
    if patch:
        for Entry in patch.TocEntries:
            try:
                l = getattr(bpy.context.scene, f"list_{Entry.TypeID}")
            except AttributeError:
                continue
            new_item = l.add()
            new_item.item_name = str(Entry.FileID)
            new_item.item_type = str(Entry.TypeID)
        
class ListItem(PropertyGroup):
    
    item_name: StringProperty(
        name="Name",
        description = "id",
        default = "0"
    )
    
    item_type: StringProperty(
        name="Type",
        description="type",
        default="0"
    )
    
class MY_UL_List(UIList):
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            entry_type = int(item.item_type)
            if entry_type == MeshID: type_icon = 'FILE_3D'
            elif entry_type == TexID: type_icon = 'FILE_IMAGE'
            elif entry_type == MaterialID: type_icon = 'MATERIAL' 
            elif entry_type == ParticleID: type_icon = 'PARTICLES'
            elif entry_type == AnimationID: type_icon = 'ARMATURE_DATA'
            elif entry_type == BoneID: type_icon = 'BONE_DATA'
            elif entry_type == WwiseBankID:  type_icon = 'OUTLINER_DATA_SPEAKER'
            elif entry_type == WwiseDepID: type_icon = 'OUTLINER_DATA_SPEAKER'
            elif entry_type == WwiseStreamID:  type_icon = 'OUTLINER_DATA_SPEAKER'
            elif entry_type == WwiseMetaDataID: type_icon = 'OUTLINER_DATA_SPEAKER'
            elif entry_type == StateMachineID: type_icon = 'DRIVER'
            elif entry_type == StringID: type_icon = 'WORDWRAP_ON'
            elif entry_type == PhysicsID: type_icon = 'PHYSICS'
            friendly_name = GetFriendlyNameFromID(int(item.item_name))
            row.label(text=friendly_name, icon = type_icon)
            if entry_type == MeshID:
                row.operator("helldiver2.archive_mesh_save", icon='FILE_BLEND', text="").object_id = item.item_name
                row.operator("helldiver2.archive_mesh_import", icon='IMPORT', text="").object_id = item.item_name
            elif entry_type == TexID:
                row.operator("helldiver2.texture_saveblendimage", icon='FILE_BLEND', text="").object_id = item.item_name
                row.operator("helldiver2.texture_import", icon='IMPORT', text="").object_id = item.item_name
            elif entry_type == MaterialID:
                row.operator("helldiver2.material_save", icon='FILE_BLEND', text="").object_id = item.item_name
                row.operator("helldiver2.material_import", icon='IMPORT', text="").object_id = item.item_name
                #row.operator("helldiver2.material_showeditor", icon='MOD_LINEART', text="").object_id = str(Entry.FileID)
                #self.draw_material_editor(Entry, box, row)
            elif entry_type == AnimationID:
                row.operator("helldiver2.archive_animation_import", icon="IMPORT", text="").object_id = item.item_name
            Entry = Global_TocManager.GetEntry(int(item.item_name), int(item.item_type))
            if Entry is None:
                return
            if Global_TocManager.IsInPatch(Entry):
                props = row.operator("helldiver2.archive_removefrompatch", icon='FAKE_USER_ON', text="")
                props.object_id     = item.item_name
                props.object_typeid = item.item_type
            else:
                props = row.operator("helldiver2.archive_addtopatch", icon='FAKE_USER_OFF', text="")
                props.object_id     = item.item_name
                props.object_typeid = item.item_type
            if Entry.IsModified:
                props = row.operator("helldiver2.archive_undo_mod", icon='TRASH', text="")
                props.object_id     = item.item_name
                props.object_typeid = item.item_type
            if Global_TocManager.IsInPatch(Entry) and Global_TocManager.ActiveArchive and not Global_TocManager.ActiveArchive.GetEntry(Entry.FileID, Entry.TypeID):
                props = row.operator("helldiver2.archive_removefrompatch", icon='X', text="")
                props.object_id     = str(Entry.FileID)
                props.object_typeid = str(Entry.TypeID)
        elif self.layout_type in {'GRID'}: 
            layout.alignment = 'CENTER'
            layout.label(text="", icon = "FILE_IMAGE")
            
    def filter_items(self, context, data, propname):
        # Get the filter string from a property, for example
        # Assuming you have a StringProperty named 'filter_string' on your UILIST instance
        data = getattr(data, propname)
        flt_flags = []
        flt_neworder = []
        if self.filter_name:
            filter_string = self.filter_name
            if filter_string.startswith("0x"):
                filter_string = str(hex_to_decimal(filter_string))
            flt_flags = bpy.types.UI_UL_list.filter_items_by_name(filter_string, self.bitflag_filter_item, data, "item_name")
        if not flt_flags:
            flt_flags = [self.bitflag_filter_item] * len(data)
        #flt_neworder = bpy.types.UI_UL_list.sort_items_by_name(data, "item_name")
        
        return flt_flags, flt_neworder

class HellDivers2ToolsPanel(Panel):
    bl_label = f"Helldivers 2 SDK: Community Edition v{bl_info['version'][0]}.{bl_info['version'][1]}.{bl_info['version'][2]}"
    bl_idname = "SF_PT_Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Modding"

    def draw_material_editor(self, Entry, layout, row):
        if Entry.IsLoaded:
            mat = Entry.LoadedData
            if mat.DEV_ShowEditor:
                for i, t in enumerate(mat.TexIDs):
                    row = layout.row(); row.separator(factor=2.0)
                    ddsPath = mat.DEV_DDSPaths[i]
                    if ddsPath != None: filepath = Path(ddsPath)
                    label = filepath.name if ddsPath != None else str(t)
                    if Entry.MaterialTemplate != None:
                        label = TextureTypeLookup[Entry.MaterialTemplate][i] + ": " + label
                    material_texture_entry = row.operator("helldiver2.material_texture_entry", icon='FILE_IMAGE', text=label, emboss=False)
                    material_texture_entry.object_id = str(t)
                    material_texture_entry.texture_index = str(i)
                    material_texture_entry.material_id = str(Entry.FileID)
                    # props = row.operator("helldiver2.material_settex", icon='FILEBROWSER', text="")
                    # props.object_id = str(Entry.FileID)
                    # props.tex_idx = i
                for i, variable in enumerate(mat.ShaderVariables):
                    row = layout.row(); row.separator(factor=2.0)
                    split = row.split(factor=0.5)
                    row = split.column()
                    row.alignment = 'RIGHT'
                    name = variable.ID
                    if variable.name != "": name = variable.name
                    row.label(text=f"{variable.klassName}: {name}", icon='OPTIONS')
                    row = split.column()
                    row.alignment = 'LEFT'
                    sections = len(variable.values)
                    if sections == 3: sections = 4 # add an extra for the color picker
                    row = row.split(factor=1/sections)
                    for j, value in enumerate(variable.values):
                        ShaderVariable = row.operator("helldiver2.material_shader_variable", text=str(round(value, 2)))
                        ShaderVariable.value = value
                        ShaderVariable.object_id = str(Entry.FileID)
                        ShaderVariable.variable_index = i
                        ShaderVariable.value_index = j
                    if len(variable.values) == 3:
                        ColorPicker = row.operator("helldiver2.material_shader_variable_color", text="", icon='EYEDROPPER')
                        ColorPicker.object_id = str(Entry.FileID)
                        ColorPicker.variable_index = i

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        row = layout.row()
        global OnCorrectBlenderVersion
        if not OnCorrectBlenderVersion:
            row.label(text="Using Incorrect Blender Version!")
            row = layout.row()
            row.label(text="Please Use Blender 4.0.X to 4.3.X")
            return
        
        if bpy.app.version[1] > 0:
            row.label(text="Warning! Soft Supported Blender Version. Issues may Occur.", icon='ERROR')


        row = layout.row()
        row.alignment = 'CENTER'
        global Global_addonUpToDate
        global Global_latestAddonVersion
        global Global_gamepathIsValid

        if Global_addonUpToDate == None:
            row.label(text="Addon Failed to Check latest Version")
        elif not Global_addonUpToDate:
            row.label(text="Addon is Outdated!")
            row.label(text=f"Latest Version: {Global_latestAddonVersion}")
            row = layout.row()
            row.alignment = 'CENTER'
            row.scale_y = 2
            row.operator("helldiver2.latest_release", icon = 'URL')
            row.separator()

        # Draw Settings, Documentation and Spreadsheet
        mainbox = layout.box()
        row = mainbox.row()
        row.prop(scene.Hd2ToolPanelSettings, "MenuExpanded",
            icon="DOWNARROW_HLT" if scene.Hd2ToolPanelSettings.MenuExpanded else "RIGHTARROW",
            icon_only=True, emboss=False, text="Settings")
        row.label(icon="SETTINGS")
        
        if scene.Hd2ToolPanelSettings.MenuExpanded or not Global_gamepathIsValid:
            row = mainbox.grid_flow(columns=2)
            row = mainbox.row(); row.separator(); row.label(text="Display Types"); box = row.box(); row = box.grid_flow(columns=1)
            row.prop(scene.Hd2ToolPanelSettings, "ShowExtras")
            row.prop(scene.Hd2ToolPanelSettings, "FriendlyNames")
            row = mainbox.row(); row.separator(); row.label(text="Import Options"); box = row.box(); row = box.grid_flow(columns=1)
            row.prop(scene.Hd2ToolPanelSettings, "ImportMaterials")
            row.prop(scene.Hd2ToolPanelSettings, "ImportLods")
            row.prop(scene.Hd2ToolPanelSettings, "ImportGroup0")
            row.prop(scene.Hd2ToolPanelSettings, "MakeCollections")
            row.prop(scene.Hd2ToolPanelSettings, "ImportCulling")
            row.prop(scene.Hd2ToolPanelSettings, "ImportStatic")
            row.prop(scene.Hd2ToolPanelSettings, "RemoveGoreMeshes")
            row.prop(scene.Hd2ToolPanelSettings, "ParentArmature")
            row.prop(scene.Hd2ToolPanelSettings, "ImportArmature")
            row = mainbox.row(); row.separator(); row.label(text="Export Options"); box = row.box(); row = box.grid_flow(columns=1)
            row.prop(scene.Hd2ToolPanelSettings, "Force3UVs")
            row.prop(scene.Hd2ToolPanelSettings, "Force1Group")
            row.prop(scene.Hd2ToolPanelSettings, "AutoLods")
            row.prop(scene.Hd2ToolPanelSettings, "SaveBonePositions")
            row.prop(scene.Hd2ToolPanelSettings, "SaveTexturesWithMaterial")
            row.prop(scene.Hd2ToolPanelSettings, "GenerateRandomTextureIDs")
            row = mainbox.row(); row.separator(); row.label(text="Other Options"); box = row.box(); row = box.grid_flow(columns=1)
            row.prop(scene.Hd2ToolPanelSettings, "SaveNonSDKMaterials")
            row.prop(scene.Hd2ToolPanelSettings, "SaveUnsavedOnWrite")
            row.prop(scene.Hd2ToolPanelSettings, "AutoSaveMeshMaterials")
            row.prop(scene.Hd2ToolPanelSettings, "PatchBaseArchiveOnly")
            row.prop(scene.Hd2ToolPanelSettings, "LegacyWeightNames")
            row.prop(scene.Hd2ToolPanelSettings, "MergeArmatures")

            #Custom Searching tools
            row = mainbox.row(); row.separator(); row.label(text="Special Tools"); box = row.box(); row = box.grid_flow(columns=1)
            # Draw Bulk Loader Extras
            row.prop(scene.Hd2ToolPanelSettings, "EnableTools")
            if scene.Hd2ToolPanelSettings.EnableTools:
                row = mainbox.row(); box = row.box(); row = box.grid_flow(columns=1)
                #row.label()
                row.label(text="WARNING! Developer Tools, Please Know What You Are Doing!")
                row.prop(scene.Hd2ToolPanelSettings, "UnloadEmptyArchives")
                row.prop(scene.Hd2ToolPanelSettings, "UnloadPatches")
                row.prop(scene.Hd2ToolPanelSettings, "LoadFoundArchives")
                #row.prop(scene.Hd2ToolPanelSettings, "DeleteOnLoadArchive")
                row = box.row()
                row.operator("helldiver2.search_by_entry", icon= 'FILEBROWSER')
                row.operator("helldiver2.bulk_load", icon= 'IMPORT', text="Bulk Load")
                row.operator("helldiver2.search_by_entry_input", icon= 'VIEWZOOM')
                #row = box.grid_flow(columns=1)
                #row.operator("helldiver2.meshfixtool", icon='MODIFIER')
                search = box.row()
                search.label(text=Global_searchpath)
                search.operator("helldiver2.change_searchpath", icon='FILEBROWSER')
                mainbox.separator()
            row = mainbox.row()
            row.label(text=Global_gamepath)
            row.operator("helldiver2.change_filepath", icon='FILEBROWSER')
            mainbox.separator()

        if not Global_gamepathIsValid:
            row = layout.row()
            row.label(text="Current Selected game filepath to data folder is not valid!")
            row = layout.row()
            row.label(text="Please select your game directory in the settings!")
            return

        # Draw Archive Import/Export Buttons
        row = layout.row(); row = layout.row()
        row.operator("helldiver2.help", icon='HELP', text="Discord")
        row.operator("helldiver2.archive_spreadsheet", icon='INFO', text="Archive IDs")
        row.operator("helldiver2.github", icon='URL', text= "")
        row = layout.row(); row = layout.row()
        row.operator("helldiver2.archive_import_default", icon= 'SOLO_ON', text="")
        row.operator("helldiver2.search_archives", icon= 'VIEWZOOM')
        row.operator("helldiver2.archive_unloadall", icon= 'FILE_REFRESH', text="")
        row = layout.row()
        row.prop(scene.Hd2ToolPanelSettings, "LoadedArchives", text="Archives")
        if scene.Hd2ToolPanelSettings.EnableTools:
            row.scale_x = 0.33
            ArchiveNum = "0/0"
            if Global_TocManager.ActiveArchive != None:
                Archiveindex = Global_TocManager.LoadedArchives.index(Global_TocManager.ActiveArchive) + 1
                Archiveslength = len(Global_TocManager.LoadedArchives)
                ArchiveNum = f"{Archiveindex}/{Archiveslength}"
            row.operator("helldiver2.next_archive", icon= 'RIGHTARROW', text=ArchiveNum)
            row.scale_x = 1
        row.operator("helldiver2.archive_import", icon= 'FILEBROWSER', text= "").is_patch = False
        row = layout.row()
        #if len(Global_TocManager.LoadedArchives) > 0:
        #    Global_TocManager.SetActiveByName(scene.Hd2ToolPanelSettings.LoadedArchives)


        # Draw Patch Stuff
        row = layout.row(); row = layout.row()

        row.operator("helldiver2.archive_createpatch", icon= 'COLLECTION_NEW', text="New Patch")
        row.operator("helldiver2.archive_export", icon= 'DISC', text="Write Patch")
        row.operator("helldiver2.export_patch", icon= 'EXPORT')
        row.operator("helldiver2.patches_unloadall", icon= 'FILE_REFRESH', text="")

        row = layout.row()
        row.prop(scene.Hd2ToolPanelSettings, "Patches", text="Patches")
        #if len(Global_TocManager.Patches) > 0:
        #    Global_TocManager.SetActivePatchByName(scene.Hd2ToolPanelSettings.Patches)
        row.operator("helldiver2.rename_patch", icon='GREASEPENCIL', text="")
        row.operator("helldiver2.archive_import", icon= 'FILEBROWSER', text="").is_patch = True

        # Draw Archive Contents
        row = layout.row(); row = layout.row()
        title = "No Archive Loaded"
        if Global_TocManager.ActiveArchive != None:
            ArchiveID = Global_TocManager.ActiveArchive.Name
            name = GetArchiveNameFromID(ArchiveID)
            title = f"{name}    ID: {ArchiveID}"
        if Global_TocManager.ActivePatch != None and scene.Hd2ToolPanelSettings.PatchOnly:
            name = Global_TocManager.ActivePatch.Name
            title = f"Patch: {name}    File: {Global_TocManager.ActivePatch.Name}"
        row.prop(scene.Hd2ToolPanelSettings, "ContentsExpanded",
            icon="DOWNARROW_HLT" if scene.Hd2ToolPanelSettings.ContentsExpanded else "RIGHTARROW",
            icon_only=True, emboss=False, text=title)
        row.prop(scene.Hd2ToolPanelSettings, "PatchOnly", text="")
        row.operator("helldiver2.copy_archive_id", icon='COPY_ID', text="")
        row.operator("helldiver2.archive_object_dump_import_by_id", icon='PACKAGE', text="")


        # Get Display Data
        DisplayData = GetDisplayData()
        DisplayTocEntries = DisplayData[0]
        DisplayTocTypes   = DisplayData[1]

        # Draw Contents
        NewFriendlyNames = []
        NewFriendlyIDs = []
        if scene.Hd2ToolPanelSettings.ContentsExpanded:
            if len(DisplayTocEntries) == 0: return

            # Draw Search Bar
            row = layout.row(); row = layout.row()
            row.prop(scene.Hd2ToolPanelSettings, "SearchField", icon='VIEWZOOM', text="")

            DrawChain = []
            for Type in DisplayTocTypes:
                # Get Type Icon
                type_icon = 'FILE'
                showExtras = scene.Hd2ToolPanelSettings.ShowExtras
                global Global_Foldouts
                if Type.TypeID == MeshID:
                    type_icon = 'FILE_3D'
                elif Type.TypeID == TexID:
                    type_icon = 'FILE_IMAGE'
                elif Type.TypeID == MaterialID:
                    type_icon = 'MATERIAL' 
                elif Type.TypeID == ParticleID:
                    type_icon = 'PARTICLES'
                elif Type.TypeID == AnimationID: 
                    type_icon = 'ARMATURE_DATA'
                elif showExtras:
                    if Type.TypeID == BoneID: type_icon = 'BONE_DATA'
                    elif Type.TypeID == WwiseBankID:  type_icon = 'OUTLINER_DATA_SPEAKER'
                    elif Type.TypeID == WwiseDepID: type_icon = 'OUTLINER_DATA_SPEAKER'
                    elif Type.TypeID == WwiseStreamID:  type_icon = 'OUTLINER_DATA_SPEAKER'
                    elif Type.TypeID == WwiseMetaDataID: type_icon = 'OUTLINER_DATA_SPEAKER'
                    elif Type.TypeID == StateMachineID: type_icon = 'DRIVER'
                    elif Type.TypeID == StringID: type_icon = 'WORDWRAP_ON'
                    elif Type.TypeID == PhysicsID: type_icon = 'PHYSICS'
                else:
                    continue
                
                
                closed = Type.TypeID not in [MaterialID, TexID, MeshID]
                panel_header, panel_body = self.layout.panel(f"hd2_panel_{Type.TypeID}", default_closed=closed)
                # Draw Type Header
                typeName = GetTypeNameFromID(Type.TypeID)
                panel_header.label(text=f"{typeName}: {Type.TypeID}")
                if panel_body:
                    panel_header.operator("helldiver2.select_type", icon='RESTRICT_SELECT_OFF', text="").object_typeid = str(Type.TypeID)
                    if typeName == "material": panel_header.operator("helldiver2.material_add", icon='FILE_NEW', text="")
                else:
                    panel_header.label(icon=type_icon)
                # Draw Type Body
                if panel_body:
                    panel_body.template_list("MY_UL_List", f"list_{Type.TypeID}", scene, f"list_{Type.TypeID}", scene, f"index_{Type.TypeID}", rows=10)
        if scene.Hd2ToolPanelSettings.FriendlyNames:  
            Global_TocManager.SavedFriendlyNames = NewFriendlyNames
            Global_TocManager.SavedFriendlyNameIDs = NewFriendlyIDs

class WM_MT_helldiver2_context_menu(Menu):
    bl_label = "Entry Context Menu"

    def draw_entry_buttons(row, Entry):
        if not Entry.IsSelected:
            Global_TocManager.SelectEntries([Entry])

        # Combine entry strings to be passed to operators
        FileIDStr = ""
        TypeIDStr = ""
        for SelectedEntry in Global_TocManager.SelectedEntries:
            FileIDStr += str(SelectedEntry.FileID)+","
            TypeIDStr += str(SelectedEntry.TypeID)+","
        # Get common class
        AreAllMeshes    = True
        AreAllTextures  = True
        AreAllMaterials = True
        AreAllParticles = True
        SingleEntry = True
        NumSelected = len(Global_TocManager.SelectedEntries)
        if len(Global_TocManager.SelectedEntries) > 1:
            SingleEntry = False
        for SelectedEntry in Global_TocManager.SelectedEntries:
            if SelectedEntry.TypeID == MeshID:
                AreAllTextures = False
                AreAllMaterials = False
                AreAllParticles = False
            elif SelectedEntry.TypeID == TexID:
                AreAllMeshes = False
                AreAllMaterials = False
                AreAllParticles = False
            elif SelectedEntry.TypeID == MaterialID:
                AreAllTextures = False
                AreAllMeshes = False
                AreAllParticles = False
            elif SelectedEntry.TypeID == ParticleID:
                AreAllTextures = False
                AreAllMeshes = False
                AreAllMaterials = False
            else:
                AreAllMeshes = False
                AreAllTextures = False
                AreAllMaterials = False
                AreAllParticles = False
        
        RemoveFromPatchName = "Remove From Patch" if SingleEntry else f"Remove {NumSelected} From Patch"
        AddToPatchName = "Add To Patch" if SingleEntry else f"Add {NumSelected} To Patch"
        ImportMeshName = "Import Mesh" if SingleEntry else f"Import {NumSelected} Meshes"
        ImportTextureName = "Import Texture" if SingleEntry else f"Import {NumSelected} Textures"
        ImportMaterialName = "Import Material" if SingleEntry else f"Import {NumSelected} Materials"
        ImportParticleName = "Import Particle" if SingleEntry else f"Import {NumSelected} Particles"
        DumpObjectName = "Export Object Dump" if SingleEntry else f"Export {NumSelected} Object Dumps"
        ImportDumpObjectName = "Import Object Dump" if SingleEntry else f"Import {NumSelected} Object Dumps"
        SaveTextureName = "Save Blender Texture" if SingleEntry else f"Save Blender {NumSelected} Textures"
        SaveMaterialName = "Save Material" if SingleEntry else f"Save {NumSelected} Materials"
        SaveParticleName = "Save Particle" if SingleEntry else f"Save {NumSelected} Particles"
        UndoName = "Undo Modifications" if SingleEntry else f"Undo {NumSelected} Modifications"
        CopyName = "Copy Entry" if SingleEntry else f"Copy {NumSelected} Entries"
        
        # Draw seperator
        row.separator()
        row.label(text=Global_SectionHeader)

        # Draw copy button
        row.separator()
        props = row.operator("helldiver2.archive_copy", icon='COPYDOWN', text=CopyName)
        props.object_id     = FileIDStr
        props.object_typeid = TypeIDStr
        if len(Global_TocManager.CopyBuffer) != 0:
            row.operator("helldiver2.archive_paste", icon='PASTEDOWN', text="Paste "+str(len(Global_TocManager.CopyBuffer))+" Entries")
            row.operator("helldiver2.archive_clearclipboard", icon='TRASH', text="Clear Clipboard")
        if SingleEntry:
            props = row.operator("helldiver2.archive_duplicate", icon='DUPLICATE', text="Duplicate Entry")
            props.object_id     = str(Entry.FileID)
            props.object_typeid = str(Entry.TypeID)
        
        if Global_TocManager.IsInPatch(Entry):
            props = row.operator("helldiver2.archive_removefrompatch", icon='X', text=RemoveFromPatchName)
            props.object_id     = FileIDStr
            props.object_typeid = TypeIDStr
        else:
            props = row.operator("helldiver2.archive_addtopatch", icon='PLUS', text=AddToPatchName)
            props.object_id     = FileIDStr
            props.object_typeid = TypeIDStr

        # Draw import buttons
        # TODO: Add generic import buttons
        row.separator()
        if AreAllMeshes:
            row.operator("helldiver2.archive_mesh_import", icon='IMPORT', text=ImportMeshName).object_id = FileIDStr
        elif AreAllTextures:
            row.operator("helldiver2.texture_import", icon='IMPORT', text=ImportTextureName).object_id = FileIDStr
        elif AreAllMaterials:
            row.operator("helldiver2.material_import", icon='IMPORT', text=ImportMaterialName).object_id = FileIDStr
        #elif AreAllParticles:
            #row.operator("helldiver2.archive_particle_import", icon='IMPORT', text=ImportParticleName).object_id = FileIDStr
        # Draw export buttons
        row.separator()

        props = row.operator("helldiver2.archive_object_dump_import", icon='PACKAGE', text=ImportDumpObjectName)
        props.object_id     = FileIDStr
        props.object_typeid = TypeIDStr
        props = row.operator("helldiver2.archive_object_dump_export", icon='PACKAGE', text=DumpObjectName)
        props.object_id     = FileIDStr
        props.object_typeid = TypeIDStr
        # Draw dump import button
        # if AreAllMaterials and SingleEntry: row.operator("helldiver2.archive_object_dump_import", icon="IMPORT", text="Import Raw Dump").object_id = FileIDStr
        # Draw save buttons
        row.separator()
        if AreAllMeshes:
            if SingleEntry:
                row.operator("helldiver2.archive_mesh_save", icon='FILE_BLEND', text="Save Mesh").object_id = str(Entry.FileID)
            else:
              row.operator("helldiver2.archive_mesh_batchsave", icon='FILE_BLEND', text=f"Save {NumSelected} Meshes")
        elif AreAllTextures:
            row.operator("helldiver2.texture_saveblendimage", icon='FILE_BLEND', text=SaveTextureName).object_id = FileIDStr
            row.separator()
            row.operator("helldiver2.texture_savefromdds", icon='FILE_IMAGE', text=f"Import {NumSelected} DDS Textures").object_id = FileIDStr
            row.operator("helldiver2.texture_savefrompng", icon='FILE_IMAGE', text=f"Import {NumSelected} PNG Textures").object_id = FileIDStr
            row.separator()
            row.operator("helldiver2.texture_batchexport", icon='OUTLINER_OB_IMAGE', text=f"Export {NumSelected} DDS Textures").object_id = FileIDStr
            row.operator("helldiver2.texture_batchexport_png", icon='OUTLINER_OB_IMAGE', text=f"Export {NumSelected} PNG Textures").object_id = FileIDStr
        elif AreAllMaterials:
            row.operator("helldiver2.material_save", icon='FILE_BLEND', text=SaveMaterialName).object_id = FileIDStr
            if SingleEntry:
                row.operator("helldiver2.material_set_template", icon='MATSHADERBALL').entry_id = str(Entry.FileID)
                if Entry.LoadedData != None:
                    row.operator("helldiver2.copytest", icon='COPY_ID', text="Copy Parent Material Entry ID").text = str(Entry.LoadedData.ParentMaterialID)
        #elif AreAllParticles:
            #row.operator("helldiver2.particle_save", icon='FILE_BLEND', text=SaveParticleName).object_id = FileIDStr
        # Draw copy ID buttons
        if SingleEntry:
            row.separator()
            row.operator("helldiver2.copytest", icon='COPY_ID', text="Copy Entry ID").text = str(Entry.FileID)
            row.operator("helldiver2.copytest", icon='COPY_ID', text="Copy Entry Hex ID").text = str(hex(Entry.FileID))
            row.operator("helldiver2.copytest", icon='COPY_ID', text="Copy Type ID").text  = str(Entry.TypeID)
            row.operator("helldiver2.copytest", icon='COPY_ID', text="Copy Friendly Name").text  = GetFriendlyNameFromID(Entry.FileID)
            if Global_TocManager.IsInPatch(Entry):
                props = row.operator("helldiver2.archive_entryrename", icon='TEXT', text="Rename")
                props.object_id     = str(Entry.FileID)
                props.object_typeid = str(Entry.TypeID)
        if Entry.IsModified:
            row.separator()
            props = row.operator("helldiver2.archive_undo_mod", icon='TRASH', text=UndoName)
            props.object_id     = FileIDStr
            props.object_typeid = TypeIDStr

        if SingleEntry:
            row.operator("helldiver2.archive_setfriendlyname", icon='WORDWRAP_ON', text="Set Friendly Name").object_id = str(Entry.FileID)
            
    def draw_material_editor_context_buttons(layout, FileID, MaterialID, TextureIndex):
        row = layout
        row.separator()
        row.label(text=Global_SectionHeader)
        row.separator()
        row.operator("helldiver2.copytest", icon='COPY_ID', text="Copy Entry ID").text = str(FileID)
        row.operator("helldiver2.copytest", icon='COPY_ID', text="Copy Entry Hex ID").text = str(hex(int(FileID)))
        row.operator("helldiver2.copytest", icon='COPY_ID', text="Copy Type ID").text  = str(TexID)
        props = row.operator("helldiver2.archive_entryrename", icon='TEXT', text="Rename")
        props.object_id     = str(FileID)
        props.object_typeid = str(TexID)
        props.material_id = str(MaterialID)
        props.texture_index = str(TextureIndex)

    def draw(self, context):
        value = getattr(context, "button_operator", None)
        menuName = type(value).__name__
        prop = getattr(context, "button_prop", None)
        if prop:
            if prop.name == "index":
                val = getattr(context.button_pointer, prop.identifier)
                collection_prop = getattr(context.button_pointer, prop.identifier.replace("index", "list"))[val]
                FileID = int(collection_prop.item_name)
                TypeID = int(collection_prop.item_type)
                WM_MT_helldiver2_context_menu.draw_entry_buttons(self.layout, Global_TocManager.GetEntry(int(FileID), int(TypeID)))
        elif menuName == "HELLDIVER2_OT_archive_entry":
            layout = self.layout
            FileID = getattr(value, "object_id")
            TypeID = getattr(value, "object_typeid")
            WM_MT_helldiver2_context_menu.draw_entry_buttons(layout, Global_TocManager.GetEntry(int(FileID), int(TypeID)))
        elif menuName == "HELLDIVER2_OT_material_texture_entry":
            layout = self.layout
            FileID = getattr(value, "object_id")
            MaterialID = getattr(value, "material_id")
            TextureIndex = getattr(value, "texture_index")
            WM_MT_helldiver2_context_menu.draw_material_editor_context_buttons(layout, FileID, MaterialID, TextureIndex)
        elif menuName == "":
            layout = self.layout
            FileID = getattr(value, "object_id")
            TypeID = getattr(value, "object_typeid")
            WM_MT_helldiver2_context_menu.draw_entry_buttons(layout, Global_TocManager.GetEntry(int(FileID), int(TypeID)))
            

#endregion

classes = (
    LoadArchiveOperator,
    PatchArchiveOperator,
    ImportStingrayMeshOperator,
    SaveStingrayMeshOperator,
    ImportStingrayAnimationOperator,
    SaveStingrayAnimationOperator,
    ImportMaterialOperator,
    ImportTextureOperator,
    ExportTextureOperator,
    DumpArchiveObjectOperator,
    ImportDumpOperator,
    Hd2ToolPanelSettings,
    HellDivers2ToolsPanel,
    UndoArchiveEntryModOperator,
    AddMaterialOperator,
    SaveMaterialOperator,
    SaveTextureFromBlendImageOperator,
    ShowMaterialEditorOperator,
    SetMaterialTexture,
    SearchArchivesOperator,
    LoadArchivesOperator,
    CopyArchiveEntryOperator,
    PasteArchiveEntryOperator,
    ClearClipboardOperator,
    SaveTextureFromDDSOperator,
    HelpOperator,
    ArchiveSpreadsheetOperator,
    UnloadArchivesOperator,
    ArchiveEntryOperator,
    CreatePatchFromActiveOperator,
    AddEntryToPatchOperator,
    RemoveEntryFromPatchOperator,
    CopyTextOperator,
    BatchExportTextureOperator,
    BatchSaveStingrayMeshOperator,
    SelectAllOfTypeOperator,
    RenamePatchEntryOperator,
    DuplicateEntryOperator,
    SetEntryFriendlyNameOperator,
    DefaultLoadArchiveOperator,
    BulkLoadOperator,
    ImportAllOfTypeOperator,
    UnloadPatchesOperator,
    GithubOperator,
    ChangeFilepathOperator,
    CopyCustomPropertyOperator,
    PasteCustomPropertyOperator,
    CopyArchiveIDOperator,
    ExportPatchAsZipOperator,
    RenamePatchOperator,
    NextArchiveOperator,
    MaterialTextureEntryOperator,
    EntrySectionOperator,
    SaveTextureFromPNGOperator,
    SearchByEntryIDOperator,
    ChangeSearchpathOperator,
    ExportTexturePNGOperator,
    BatchExportTexturePNGOperator,
    CopyDecimalIDOperator,
    CopyHexIDOperator,
    GenerateEntryIDOperator,
    SetMaterialTemplateOperator,
    LatestReleaseOperator,
    MaterialShaderVariableEntryOperator,
    MaterialShaderVariableColorEntryOperator,
    MeshFixOperator,
    ImportStingrayParticleOperator,
    SaveStingrayParticleOperator,
    ImportDumpByIDOperator,
    SearchByEntryIDInput,
)

Global_TocManager = TocManager()

class DotDict(dict):
        
    def __getattr__(self, name):
        return dict.__getitem__(self, name)
        
    def __setattr__(self, name, value):
        dict.__setitem__(self, name, value)
    

def register():
    if not os.path.exists(Global_texconvpath): raise Exception("Texconv is not found, please install Texconv in /deps/")
    CheckBlenderVersion()
    CheckAddonUpToDate()
    InitializeConfig()
    UpdateArchiveHashes()
    LoadTypeHashes()
    LoadNameHashes()
    LoadArchiveHashes()
    LoadShaderVariables(Global_variablespath)
    LoadBoneHashes(Global_bonehashpath, Global_BoneNames)
    for cls in classes:
        bpy.utils.register_class(cls)
    Scene.Hd2ToolPanelSettings = PointerProperty(type=Hd2ToolPanelSettings)
    bpy.utils.register_class(WM_MT_helldiver2_context_menu)
    bpy.types.UI_MT_list_item_context_menu.prepend(WM_MT_helldiver2_context_menu.draw)
    bpy.types.VIEW3D_MT_object_context_menu.append(CustomPropertyContext)
    bpy.utils.register_class(MY_UL_List)
    bpy.utils.register_class(ListItem)
    bpy.types.Scene.type_lists = DotDict()
    bpy.types.Scene.type_indices = DotDict()
    for t in Global_TypeIDs:
        setattr(bpy.types.Scene, f"list_{t}", CollectionProperty(type = ListItem))
        setattr(bpy.types.Scene, f"index_{t}", IntProperty(name = "index", default = 0))
        #bpy.types.Scene[f"list_{t}"] = CollectionProperty(type = ListItem)
        #bpy.types.Scene[f"index_{t}"] = IntProperty(name = "", default = 0)
    #bpy.types.Scene.texture_list = CollectionProperty(type = ListItem)
    #bpy.types.Scene.texture_index = IntProperty(name = "", default = 0)
    #bpy.types.Scene.material_list = CollectionProperty(type = ListItem)
    #bpy.types.Scene.material_index = IntProperty(name = "", default = 0)
    #bpy.types.Scene.animation_list = CollectionProperty(type = ListItem)
    #bpy.types.Scene.animation_index = IntProperty(name = "", default = 0)
    #bpy.types.Scene.particle_list = CollectionProperty(type = ListItem)
    #bpy.types.Scene.particle_index = IntProperty(name = "", default = 0)
    #bpy.types.Scene.unit_list = CollectionProperty(type = ListItem)
    #bpy.types.Scene.unit_index = IntProperty(name = "", default = 0)
    

def unregister():
    bpy.utils.unregister_class(WM_MT_button_context)
    del Scene.Hd2ToolPanelSettings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.types.VIEW3D_MT_object_context_menu.remove(CustomPropertyContext)
    for t in Global_TypeIDs:
        delattr(bpy.types.Scene, f"list_{t}")
        delattr(bpy.types.Scene, f"index_{t}")
    #del bpy.types.Scene.type_lists
    #del bpy.types.Scene.type_indices
    #del bpy.types.Scene.texture_list 
    #del bpy.types.Scene.texture_index
    #del bpy.types.Scene.material_list
    #del bpy.types.Scene.material_index
    #del bpy.types.Scene.animation_list
    #del bpy.types.Scene.animation_index
    #del bpy.types.Scene.particle_list
    #del bpy.types.Scene.particle_index
    #del bpy.types.Scene.unit_list
    #del bpy.types.Scene.unit_index
    bpy.utils.unregister_class(MY_UL_List)
    bpy.utils.unregister_class(ListItem)

if __name__=="__main__":
    register()
