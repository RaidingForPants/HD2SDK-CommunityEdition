import ctypes
import os

from .memoryStream import MemoryStream

AddonPath = os.path.dirname(__file__)

Global_dllpath = f"{AddonPath}\\deps\\HDTool_Helper.dll"
Global_palettepath = f"{AddonPath}\\deps\\NormalPalette.dat"

Global_CPPHelper = ctypes.cdll.LoadLibrary(Global_dllpath) if os.path.isfile(Global_dllpath) else None

def RegisterCPPHelper():
    if Global_CPPHelper == None: raise Exception("HDTool_Helper is required by the addon but failed to load!")
    return

def UnregisterCPPHelper():
    global Global_CPPHelper
    del Global_CPPHelper
    return

def LoadNormalPalette():
    Global_CPPHelper.dll_LoadPalette(Global_palettepath.encode())

def NormalsFromPalette(normals):
    f = MemoryStream(IOMode = "write")
    normals = [f.vec3_float(normal) for normal in normals]
    output    = bytearray(len(normals)*4)
    c_normals = ctypes.c_char_p(bytes(f.Data))
    c_output  = (ctypes.c_char * len(output)).from_buffer(output)
    Global_CPPHelper.dll_NormalsFromPalette(c_output, c_normals, ctypes.c_uint32(len(normals)))
    F = MemoryStream(output, IOMode = "read")
    return [F.uint32(0) for normal in normals]

def Hash32(string):
    output    = bytearray(4)
    c_output  = (ctypes.c_char * len(output)).from_buffer(output)
    Global_CPPHelper.dll_Hash32(c_output, string.encode())
    F = MemoryStream(output, IOMode = "read")
    return F.uint32(0)

def Hash64(string):
    output    = bytearray(8)
    c_output  = (ctypes.c_char * len(output)).from_buffer(output)
    Global_CPPHelper.dll_Hash64(c_output, string.encode())
    F = MemoryStream(output, IOMode = "read")
    return F.uint64(0)
