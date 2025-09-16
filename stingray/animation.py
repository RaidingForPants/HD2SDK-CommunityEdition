import bpy, bpy_types
from math import ceil, sqrt
import mathutils

from ..logger import PrettyPrint
from ..memoryStream import MemoryStream

class SkeletonMismatchException(Exception):
    pass

class AnimationEntry:
    def __init__(self):
        self.type = 0
        self.subtype = 0
        self.bone = 0
        self.time = 0
        self.data = []
        self.data2 = []
        
    def Serialize(self, tocFile):
        if tocFile.IsReading():
            self.load(tocFile)
        else:
            self.save(tocFile)
            
    def load(self, tocFile):
        # load header
        data = [0, 0, 0, 0]
        bone = 0
        time = 0
        timeMs = 0
        temp = 0
        temp_arr = []
        subtype = 0
        data = tocFile.vec4_uint8(data)
        type = (data[1] & 0xC0) >> 6
        if type == 0:
            tocFile.seek(tocFile.tell()-4)
            subtype = tocFile.uint16(subtype)
            if subtype != 3:
                bone = tocFile.uint32(bone)
                time = tocFile.float32(time) * 1000
        else:
            bone = ((data[0] & 0xf0) >> 4) | ((data[1] & 0x3f) << 4)
            time = ((data[0] & 0xf) << 16) | (data[3] << 8) | data[2]
            
        if type == 3:
            data2 = AnimationBoneInitialState.decompress_rotation(tocFile.uint32(temp))
            # rotation data
        elif type == 2:
            # position data
            data2 = AnimationBoneInitialState.decompress_position([tocFile.uint16(temp) for _ in range(3)])
        elif type == 1:
            # scale data
            data2 = AnimationBoneInitialState.decompress_scale(tocFile.vec3_half(temp_arr))
        else:
            if subtype == 4:
                # position data (uncompressed)
                data2 = tocFile.vec3_float(temp_arr)
            elif subtype == 5:
                # rotation data (uncompressed)
                data2 = [tocFile.float32(temp) for _ in range(4)]
            elif subtype == 6:
                # scale data (uncompressed)
                data2 = tocFile.vec3_float(temp_arr)
            else:
                PrettyPrint(f"Unknown type/subtype! {type}/{subtype}")
                self.subtype = subtype
                self.type = type
                return
            #elif subtype != 2:
            #    pass
        self.data2 = data2
        self.data = data
        self.bone = bone
        self.subtype = subtype
        self.type = type
        self.time = time
        
    def save(self, tocFile):
        # load header
        data = [0, 0, 0, 0]
        bone = 0
        time = 0
        timeMs = 0
        temp = 0
        temp_arr = []
        subtype = 0
        #data = tocFile.vec4_uint8(self.data)
        new_data = [0, 0, 0, 0]
        new_data[1] |= (self.type << 6) & 0xC0
        #type = (data[1] & 0xC0) >> 6
        
        if self.type == 0:
            #tocFile.seek(tocFile.tell()-4)
            subtype = tocFile.uint16(self.subtype)
            if subtype != 3:
                bone = tocFile.uint32(self.bone)
                time = tocFile.float32(self.time/1000)
        else:
            new_data[0] |= (self.bone << 4) & 0xf0
            new_data[1] |= (self.bone >> 4) & 0x3f
            #bone = ((data[0] & 0xf0) >> 4) | ((data[1] & 0x3f) << 4)
            new_data[0] |= (self.time >> 16) & 0xf
            new_data[3] = (self.time >> 8) & 0xff
            new_data[2] = (self.time & 0xff)
            #time = ((data[0] & 0xf) << 16) | (data[3] << 8) | data[2]
            tocFile.vec4_uint8(new_data)
            
            
        if self.type == 3:
           # data2 = AnimationBoneInitialState.compress_rotation(tocFile.uint32(temp))
            tocFile.uint32(AnimationBoneInitialState.compress_rotation(self.data2))
            # rotation data
        elif self.type == 2:
            # position data
            #data2 = AnimationBoneInitialState.decompress_position([tocFile.uint16(temp) for _ in range(3)])
            data2 = AnimationBoneInitialState.compress_position(self.data2)
            for value in data2:
                tocFile.uint16(value)
        elif self.type == 1:
            # scale data
            #data2 = AnimationBoneInitialState.decompress_scale(tocFile.vec3_float(temp_arr))
            data2 = AnimationBoneInitialState.compress_scale(self.data2)
            tocFile.vec3_half(data2)
        else:
            if subtype == 4:
                # position data (uncompressed)
                tocFile.vec3_float(self.data2)
                #data2 = tocFile.vec3_float(temp_arr)
            elif subtype == 5:
                # rotation data (uncompressed)
                for value in self.data2:
                    tocFile.float32(value)
                #data2 = [tocFile.float32(temp) for _ in range(4)]
            elif subtype == 6:
                # scale data (uncompressed)
                #data2 = tocFile.vec3_float(temp_arr)
                tocFile.vec3_float(self.data2)
            elif subtype != 2:
                pass
 
    
class AnimationBoneInitialState:
    def __init__(self):
        self.compressed_position = True
        self.compressed_rotation = True
        self.compressed_scale = True
        self.position = [0, 0, 0]
        self.rotation = [0, 0, 0, 0]
        self.scale = [1, 1, 1]
        
    def compress_position(position):
        return [int((pos * 3276.7) + 32767.0) for pos in position]
        
    def compress_rotation(rotation):
        if max(rotation) == rotation[0]:
            largest_idx = 0
        if max(rotation) == rotation[1]:
            largest_idx = 1
        if max(rotation) == rotation[2]:
            largest_idx = 2
        if max(rotation) == rotation[3]:
            largest_idx = 3
        cmp_rotation = 0
        first = rotation[(largest_idx+1)%4]
        first = int(((first / 0.75) * 512) + 512)
        cmp_rotation |= ((first & 0x3ff) << 2)
        second = rotation[(largest_idx+2)%4]
        second = int(((second / 0.75) * 512) + 512)
        cmp_rotation |= ((second & 0x3ff) << 12)
        third = rotation[(largest_idx+3)%4]
        third = int(((third / 0.75) * 512) + 512)
        cmp_rotation |= ((third & 0x3ff) << 22)
        cmp_rotation |= largest_idx
        return cmp_rotation
        
    def compress_scale(scale):
        return scale
        
    def decompress_position(position): # vector of 3 uint16 -> vector of 3 float32
        return [(pos - 32767.0) * (10.0/32767.0) for pos in position]
        
    def decompress_rotation(rotation): # uint32 -> vector of 4 float32
        first = (((rotation & 0xffc) >> 2) - 512.0) / 512.0 * 0.75
        second = (((rotation & 0x3ff000) >> 12) - 512.0) / 512.0 * 0.75
        third = (((rotation & 0xffc00000) >> 22) - 512.0) / 512.0 * 0.75
        largest_idx = rotation & 0x3
        largest_val = sqrt(1 - third**2 - second**2 - first**2)
        if largest_idx == 0:
            return [largest_val, first, second, third]
        elif largest_idx == 1:
            return [third, largest_val, first, second]
        elif largest_idx == 2:
            return [second, third, largest_val, first]
        elif largest_idx == 3:
            return [first, second, third, largest_val]
        
    def decompress_scale(scale): # vec3_float
        return scale
        
    def __repr__(self):
        s = ""
        s += f"Position {self.position} Rotation {self.rotation} Scale {self.scale}"
        return s
        
class BitArray:
    def __init__(self, data=bytearray()):
        self.data = []
        for b in data:
            for x in reversed(range(8)):
                self.data.append((b >> x) & 1)
        
    def get(self, index):
        return self.data[index]
        
    def to_hex(self):
        hex_string = ""
        for x in range(int(len(self.data)/4)):
            slice = self.data[(x*4):(x*4)+4]
            val = 0
            for x in range(4):
                bit = slice[x]
                if bit:
                    val += 1
                if x != 3:
                    val = val << 1
            hex_string += hex(val)[2]
        return hex_string
            
class StingrayAnimation:
    
    def __init__(self):
        self.initial_bone_states = []
        self.entries = []
        self.hashes = []
        self.hashes2 = []
        self.hashes_count = 0
        self.hashes2_count = 0
        self.unk = 0
        self.unk2 = 0
        self.bone_count = 0
        self.animation_length = 0
        self.file_size = 0
        
    def Serialize(self, tocFile):
        if tocFile.IsReading():
            self.load(tocFile)
        else:
            self.save(tocFile)
        
    def load(self, tocFile):
        temp = 0
        temp_arr = []
        self.unk = tocFile.uint32(temp)
        self.bone_count = tocFile.uint32(temp)
        self.animation_length = tocFile.float32(temp)
        self.file_size = tocFile.uint32(temp)
        self.hashes_count = tocFile.uint32(temp)
        self.hashes2_count = tocFile.uint32(temp)
        self.hashes = []
        for _ in range(self.hashes_count):
            self.hashes.append(tocFile.uint64(temp))
        self.hashes2 = []
        for _ in range(self.hashes2_count):
            self.hashes2.append(tocFile.uint64(temp))
        self.unk2 = tocFile.uint16(temp)
        num_bytes = ceil(3 * self.bone_count / 8)
        if num_bytes % 2 == 1:
            num_bytes += 1
        byte_data = tocFile.bytes(temp_arr, size=num_bytes)
        self.byte_data = bytearray(byte_data)
        for x in range(len(byte_data)):
            byte_value = byte_data[x]
            reversed_byte = 0
            for i in range(8):
                if (byte_value >> i) & 1:
                    reversed_byte |= (1 << (7 - i))
            byte_data[x] = reversed_byte
        bit_array = BitArray(byte_data)
        for x in range(self.bone_count):
            bone_state = AnimationBoneInitialState()
            bone_state.compress_position = bit_array.get(x*3)
            bone_state.compress_rotation = bit_array.get(x*3+1)
            bone_state.compress_scale = bit_array.get(x*3+2)
            if bone_state.compress_position:
                bone_state.position = AnimationBoneInitialState.decompress_position([tocFile.uint16(temp) for _ in range(3)])
            else:
                bone_state.position = tocFile.vec3_float(temp_arr)
            if bone_state.compress_rotation:
                bone_state.rotation = AnimationBoneInitialState.decompress_rotation(tocFile.uint32(temp))
            else:
                bone_state.rotation = [tocFile.float32(temp) for _ in range(4)]
            if bone_state.compress_scale:
                bone_state.scale = AnimationBoneInitialState.decompress_scale(tocFile.vec3_half(temp_arr))
            else:
                bone_state.scale = tocFile.vec3_float(temp_arr)
            self.initial_bone_states.append(bone_state)
        count = 1
        while tocFile.uint16(temp) != 3:
            count += 1
            tocFile.seek(tocFile.tell()-2)
            entry = AnimationEntry()
            entry.Serialize(tocFile)
            if not (entry.type == 0 and entry.subtype not in [4, 5, 6]):
                self.entries.append(entry)
        
        
    def save(self, tocFile):
        temp = 0
        temp_arr = []
        tocFile.uint32(self.unk)
        tocFile.uint32(self.bone_count)
        tocFile.float32(self.animation_length)
        tocFile.uint32(self.file_size)
        tocFile.uint32(self.hashes_count)
        tocFile.uint32(self.hashes2_count)
        for value in self.hashes:
            tocFile.uint64(value)
        for value in self.hashes2:
            tocFile.uint64(value)
        tocFile.uint16(self.unk2)
        bit_arr = []
        for bone_state in self.initial_bone_states:
            bit_arr.append(bone_state.compress_position)
            bit_arr.append(bone_state.compress_rotation)
            bit_arr.append(bone_state.compress_scale)
        while len(bit_arr) % 8 != 0:
            bit_arr.append(0)
        bit_array = BitArray()
        bit_array.data = bit_arr
        hex_val = bit_array.to_hex()
        byte_data = bytearray.fromhex(hex_val)
        for x in range(len(byte_data)):
            byte_value = byte_data[x]
            reversed_byte = 0
            for i in range(8):
                if (byte_value >> i) & 1:
                    reversed_byte |= (1 << (7 - i))
            byte_data[x] = reversed_byte
        #bit_array = BitArray(byte_data)
        tocFile.bytes(byte_data)
        if tocFile.tell() % 2 == 1:
            tocFile.seek(tocFile.tell()+1)
        for bone_state in self.initial_bone_states:
            if bone_state.compress_position:
                for pos in AnimationBoneInitialState.compress_position(bone_state.position):
                    tocFile.uint16(pos)
            else:
                tocFile.vec3_float(bone_state.position)
            if bone_state.compress_rotation:
                tocFile.uint32(AnimationBoneInitialState.compress_rotation(bone_state.rotation))
            else:
                for value in bone_state.rotation:
                    tocFile.float32(value)
            if bone_state.compress_scale:
                tocFile.vec3_half(AnimationBoneInitialState.compress_scale(bone_state.scale))
            else:
                tocFile.vec3_float(bone_state.scale)
        count = 1
        for entry in self.entries:
            count += 1
            entry.Serialize(tocFile)
        tocFile.uint16(0x03)
        size = tocFile.uint32(tocFile.tell())
        
        # repeat for some reason
        tocFile.uint32(self.unk)
        tocFile.uint32(self.bone_count)
        tocFile.float32(self.animation_length)
        #tocFile.uint32(self.file_size)
        tocFile.seek(tocFile.tell()+4)
        tocFile.uint32(self.hashes_count)
        tocFile.uint32(self.hashes2_count)
        for value in self.hashes:
            tocFile.uint64(value)
        for value in self.hashes2:
            tocFile.uint64(value)
        tocFile.uint16(self.unk2)
        tocFile.bytes(byte_data)
        for bone_state in self.initial_bone_states:
            if bone_state.compress_position:
                for pos in AnimationBoneInitialState.compress_position(bone_state.position):
                    tocFile.uint16(pos)
            else:
                tocFile.vec3_float(bone_state.position)
            if bone_state.compress_rotation:
                tocFile.uint32(AnimationBoneInitialState.compress_rotation(bone_state.rotation))
            else:
                for value in bone_state.rotation:
                    tocFile.float32(value)
            if bone_state.compress_scale:
                tocFile.vec3_half(AnimationBoneInitialState.compress_scale(bone_state.scale))
            else:
                tocFile.vec3_float(bone_state.scale)
        count = 1
        for entry in self.entries:
            count += 1
            entry.Serialize(tocFile)
        tocFile.uint16(0x03)
        tocFile.uint32(size)
        
    def get_initial_bone_data(self, context, armature):
        pass
        
    def utilityGetQuatKeyValue(object):
        if object.parent is not None:
            return (object.parent.matrix.to_3x3().inverted() @ object.matrix.to_3x3()).to_quaternion()
        else:
            return object.matrix.to_quaternion()
            
    def utilityResolveObjectTarget(objects, path):
        for object in objects:
            try:
                return (object, object.path_resolve(path, False))
            except:
                continue

        return None


    def utilityGetSimpleKeyValue(object, property):
        if property == "location":
            if object.parent is not None:
                return object.parent.matrix.inverted() @ object.matrix.translation
            else:
                return object.matrix_basis.translation
        elif property == "scale":
            return object.scale
        return None

    def load_from_armature(self, context, armature, bones_data):
        self.entries.clear()
        self.initial_bone_states.clear()
        action = armature.animation_data.action
        action.use_fake_user = True
        idx = bones_data.index(b"StingrayEntityRoot")
        temp = bones_data[idx:]
        splits = temp.split(b"\x00")
        bone_names = []
        for item in splits:
            if item != b'':
                bone_names.append(item.decode('utf-8'))
        bone_to_index = {bone: bone_names.index(bone) for bone in bone_names}
        index_to_bone = bone_names
        initial_bone_data = {}
        bone_parents = {}
        curves = {}
        bpy.ops.object.mode_set(mode="POSE")
        context.scene.frame_set(0)
        # initial bone data = anim frame 0
        objects = bpy.data.objects
        for curve in action.fcurves:
            result = StingrayAnimation.utilityResolveObjectTarget(objects, curve.data_path)

            if result is None:
                continue
            else:
                (object, target) = result

            # Right now, only support bone keys. Eventually, we will also check for BlendShape keys, and visibility keys.
            if type(target.data) != bpy_types.PoseBone:
                continue

            poseBone = target.data
            
            #position = StingrayAnimation.utilityGetSimpleKeyValue(
            #                target, "location") * 0.01
            #quat = StingrayAnimation.utilityGetQuatKeyValue(target)

            if poseBone.parent is not None:
                bone_parents[poseBone.name] = poseBone.parent.name
                mat = (poseBone.parent.matrix.inverted() @ poseBone.matrix)
            else:
                bone_parents[poseBone.name] = ""
                mat = poseBone.matrix
            (position, rotation, scale) = mat.decompose()
            rotation = (rotation[1], rotation[2], rotation[3], rotation[0])
            #position /= 100
            position = list(position)
            scale = list(scale)
            initial_bone_data[poseBone.name] = {'position': position, 'rotation': rotation, 'scale': scale}
            
        for bone_name in bone_names:
            bone = initial_bone_data[bone_name]
            initial_state = AnimationBoneInitialState()
            initial_state.compress_position = 0
            initial_state.compress_rotation = 0
            initial_state.compress_scale = 0
            initial_state.position = bone['position']
            initial_state.rotation = bone['rotation']
            initial_state.scale = bone['scale']
            self.initial_bone_states.append(initial_state)
            
        
            
        for curve in action.fcurves:
            result = StingrayAnimation.utilityResolveObjectTarget(objects, curve.data_path)

            if result is None:
                continue
            else:
                (object, target) = result

            # Right now, only support bone keys. Eventually, we will also check for BlendShape keys, and visibility keys.
            if type(target.data) != bpy_types.PoseBone:
                continue

            poseBone = target.data

            if target == poseBone.location.owner:
                result = curves.get(poseBone, [])
                result.append(
                    (curve, "location", curve.array_index))
                curves[poseBone] = result
            elif target == poseBone.rotation_quaternion.owner or target == poseBone.rotation_euler.owner:
                result = curves.get(poseBone, [])
                result.append(
                    (curve, "rotation_quaternion", curve.array_index))
                curves[poseBone] = result
            elif target == poseBone.scale.owner:
                result = curves.get(poseBone, [])
                result.append(
                    (curve, "scale", curve.array_index))
                curves[poseBone] = result
        length_frames = 0
        # Iterate on the target/curves and generate the proper cast curves.
        for target, curves in curves.items():
            if target.name not in bone_names:
                continue
            # We must handle quaternions separately, and key them together.
            if context.scene.Hd2ToolPanelSettings.SaveBonePositions:
                locations = [x for x in curves if x[1] == "location"]
                
                for (curve, property, index) in locations:

                    keyframes = [int(x.co[0]) for x in curve.keyframe_points]
                    keyframes = sorted(list(set(keyframes)))

                    keyvalues = []
                    scale = 1
                    
                    frames = [i for i in range(max(keyframes)+1)]

                    for frame in frames:
                        context.scene.frame_set(frame)
                        keyvalues.append(StingrayAnimation.utilityGetSimpleKeyValue(
                            target, property) * scale)
                            
                    # create position entry
                    for frame_num, value in zip(frames, keyvalues):
                        if frame_num > length_frames:
                            length_frames = frame_num
                        new_entry = AnimationEntry()
                        new_entry.bone = bone_to_index[target.name]
                        new_entry.type = 0
                        new_entry.subtype = 4
                        new_entry.data2 = value
                        new_entry.time =  int(1000 * frame_num / 30)
                        self.entries.append(new_entry)
                    break
            
            rotationQuaternion = [
                x for x in curves if x[1] == "rotation_quaternion"]
            
            quat_vals = {}
            count = 0
            for (curve, property, index) in rotationQuaternion:
                for x in curve.keyframe_points:
                    if x.co[0] not in quat_vals:
                        quat_vals[x.co[0]] = []
                    quat_vals[x.co[0]].append(x.co[1])
            bpy.ops.object.mode_set(mode="EDIT")
            b = armature.data.edit_bones[target.name]
            for frame, quat in quat_vals.items():
                if frame > length_frames:
                    length_frames = int(frame)
                new_entry = AnimationEntry()
                new_entry.bone = bone_to_index[target.name]
                new_entry.type = 0
                new_entry.subtype = 5
                value = mathutils.Quaternion(quat)
                if b.parent is not None:
                    inv_parent = b.parent.matrix.to_3x3().inverted()
                    rest_quat = (inv_parent @ b.matrix.to_3x3()).to_quaternion()
                else:
                    rest_quat = b.matrix.to_quaternion()
                value = rest_quat @ value
                new_entry.data2 = [value.x, value.y, value.z, value.w]
                new_entry.time =  int(1000 * frame / 30)
                self.entries.append(new_entry)
            
            bpy.ops.object.mode_set(mode="POSE")

            
        self.entries = sorted(self.entries, key=lambda e: e.time)            
        self.animation_length = length_frames / 30
        self.bone_count = len(self.initial_bone_states)
        bpy.ops.object.mode_set(mode="OBJECT")
        context.scene.frame_end = length_frames + 1
        
        output_stream = MemoryStream(IOMode="write")
        self.Serialize(output_stream)
        self.file_size = len(output_stream.Data)
        
    def utilityClearKeyframePoints(fcurve):
        if utilityIsVersionAtLeast(4, 0):
            return fcurve.keyframe_points.clear()

        for keyframe in reversed(fcurve.keyframe_points.values()):
            fcurve.keyframe_points.remove(keyframe)


    def utilityAddKeyframe(fcurve, frame, value, interpolation):
        keyframe = \
            fcurve.keyframe_points.insert(frame, value=value, options={'FAST'})
        keyframe.interpolation = interpolation
        
    def utilityGetOrCreateCurve(fcurves, poseBones, name, curve):
        if not name in poseBones:
            return None

        bone = poseBones[name]

        return fcurves.find(data_path="pose.bones[\"%s\"].%s" %
                            (bone.name, curve[0]), index=curve[1]) or fcurves.new(data_path="pose.bones[\"%s\"].%s" %
                                                                                  (bone.name, curve[0]), index=curve[1], action_group=bone.name)
            
        
    def to_action(self, context, armature, bones_data, animation_id):
        
        idx = bones_data.index(b"StingrayEntityRoot")
        temp = bones_data[idx:]
        splits = temp.split(b"\x00")
        bone_names = []
        for item in splits:
            if item != b'':
                bone_names.append(item.decode('utf-8'))
        if len(self.initial_bone_states) != int.from_bytes(bones_data[0:4], "little"):
            raise SkeletonMismatchException("This animation is not for this armature")
        
        PrettyPrint(f"Creaing action with ID: {animation_id}")
        actions = bpy.data.actions
        action = actions.new(str(animation_id))
        action.use_fake_user = True
        armature.animation_data.action = action
        
        fcurves = action.fcurves
        for curve in fcurves:
            curve.keyframe_points.clear()
        bone_to_index = {bone: bone_names.index(bone) for bone in bone_names}
        index_to_bone = bone_names
        initial_bone_data = {}
        bone_parents = {}
        curves = {}
        edit_bones = [b for b in armature.data.edit_bones if b.name in bone_names]
        bpy.ops.object.mode_set(mode="EDIT")
        
        for bone_index, initial_state in enumerate(self.initial_bone_states):
            bone_name = index_to_bone[bone_index]
            if bone_name not in armature.data.edit_bones:
                continue
            bone = armature.data.edit_bones[bone_name]
            
            # set initial position
            location_curves = [StingrayAnimation.utilityGetOrCreateCurve(fcurves, armature.data.edit_bones, bone_name, x) for x in [
                ("location", 0), ("location", 1), ("location", 2)]]
            if bone.parent is None:
                translation = bone.matrix.translation
            else:
                translation = (bone.parent.matrix.inverted() @ bone.matrix).translation
            initial_bone_translation = mathutils.Vector(translation)
            translation_data = mathutils.Vector(initial_state.position)
            translation_data = translation_data - initial_bone_translation
            translation_data = bone.matrix.inverted().to_quaternion() @ translation_data
            StingrayAnimation.utilityAddKeyframe(location_curves[0], 0, translation_data[0], "LINEAR")
            StingrayAnimation.utilityAddKeyframe(location_curves[1], 0, translation_data[1], "LINEAR")
            StingrayAnimation.utilityAddKeyframe(location_curves[2], 0, translation_data[2], "LINEAR")
            
            # set initial rotation
            if bone.parent is not None:
                inv_parent = bone.parent.matrix.to_3x3().inverted()
                inv_rest_quat = (inv_parent @ bone.matrix.to_3x3()).to_quaternion().inverted()
            else:
                inv_rest_quat = bone.matrix.to_quaternion().inverted()
            rotation_curves = [StingrayAnimation.utilityGetOrCreateCurve(fcurves, armature.data.edit_bones, bone_name, x) for x in [
                ("rotation_quaternion", 0), ("rotation_quaternion", 1), ("rotation_quaternion", 2), ("rotation_quaternion", 3)]]
            rotation = inv_rest_quat @ mathutils.Quaternion([initial_state.rotation[3], initial_state.rotation[0], initial_state.rotation[1], initial_state.rotation[2]])
            # Stingray is x, y, z, w
            # Blender is w, x, y, z
            StingrayAnimation.utilityAddKeyframe(rotation_curves[0], 0, rotation[0], "LINEAR") # w
            StingrayAnimation.utilityAddKeyframe(rotation_curves[1], 0, rotation[1], "LINEAR") # x
            StingrayAnimation.utilityAddKeyframe(rotation_curves[2], 0, rotation[2], "LINEAR") # y
            StingrayAnimation.utilityAddKeyframe(rotation_curves[3], 0, rotation[3], "LINEAR") # z
            
        # sort animation entries by bone:
        location_entries = {index_to_bone[bone]: [entry for entry in self.entries if entry.bone == bone and (entry.type == 2 or entry.subtype == 4)] for bone in range(len(bone_names))}
        rotation_entries = {index_to_bone[bone]: [entry for entry in self.entries if entry.bone == bone and (entry.type == 3 or entry.subtype == 5)] for bone in range(len(bone_names))}
        length_frames = 0
        for bone, locations in location_entries.items():
            if bone not in armature.data.edit_bones:
                continue
            # create location curves for bone
            b = armature.data.edit_bones[bone]
            if b.parent is None:
                translation = b.matrix.translation
            else:
                translation = (b.parent.matrix.inverted() @ b.matrix).translation
            location_curves = [StingrayAnimation.utilityGetOrCreateCurve(fcurves, armature.data.edit_bones, bone, x) for x in [
            ("location", 0), ("location", 1), ("location", 2)]]
            initial_bone_translation = mathutils.Vector(translation)
            for keyframe, location_entry in enumerate(locations):
                translation_data = mathutils.Vector(location_entry.data2)
                translation_data = translation_data - initial_bone_translation # offset from edit bone location
                translation_data = b.matrix.inverted().to_quaternion() @ translation_data
                StingrayAnimation.utilityAddKeyframe(location_curves[0], 30 * location_entry.time / 1000, translation_data[0], "LINEAR")
                StingrayAnimation.utilityAddKeyframe(location_curves[1], 30 * location_entry.time / 1000, translation_data[1], "LINEAR")
                StingrayAnimation.utilityAddKeyframe(location_curves[2], 30 * location_entry.time / 1000, translation_data[2], "LINEAR")
                length_frames = max([length_frames, int(30*location_entry.time/1000)])
                
        # interpolate better than Blender's default interpolation:
        # must turn rotation data from the animation into a keyframe every frame
        
        interpolated_rotations = {}
        nextFrame = 0
        frame = 0
        
        for bone, rotations in rotation_entries.items():
            if bone not in armature.data.edit_bones:
                continue
            i_rot = []
            b = armature.data.edit_bones[bone]
            r = self.initial_bone_states[bone_to_index[bone]].rotation
            rotation = mathutils.Quaternion([r[3], r[0], r[1], r[2]])
            for rotation_entry in rotations:
                nextFrame = int(30*rotation_entry.time/1000)
                next_rotation = mathutils.Quaternion([rotation_entry.data2[3], rotation_entry.data2[0], rotation_entry.data2[1], rotation_entry.data2[2]])
                for f in range(frame+1, nextFrame+1):
                    i_rot.append(rotation.slerp(next_rotation, (f-frame)/(nextFrame-frame)))
                frame = nextFrame
                rotation = next_rotation
            i_rot.append(rotation)
            interpolated_rotations[bone] = i_rot
                
        for bone, rotations in rotation_entries.items():
            if bone not in armature.data.edit_bones:
                continue
            # create location curves for bone
            b = armature.data.edit_bones[bone]
            #pose_bone.matrix_basis.identity()
            if b.parent is not None:
                inv_parent = b.parent.matrix.to_3x3().inverted()
                inv_rest_quat = (inv_parent @ b.matrix.to_3x3()).to_quaternion().inverted()
            else:
                inv_rest_quat = b.matrix.to_quaternion().inverted()
            rotation_curves = [StingrayAnimation.utilityGetOrCreateCurve(fcurves, armature.data.edit_bones, bone, x) for x in [
                ("rotation_quaternion", 0), ("rotation_quaternion", 1), ("rotation_quaternion", 2), ("rotation_quaternion", 3)]]
            for keyframe, rotation in enumerate(interpolated_rotations[bone]):
                quat = inv_rest_quat @ rotation
                StingrayAnimation.utilityAddKeyframe(rotation_curves[0], keyframe, quat[0], "LINEAR") # w
                StingrayAnimation.utilityAddKeyframe(rotation_curves[1], keyframe, quat[1], "LINEAR") # x
                StingrayAnimation.utilityAddKeyframe(rotation_curves[2], keyframe, quat[2], "LINEAR") # y
                StingrayAnimation.utilityAddKeyframe(rotation_curves[3], keyframe, quat[3], "LINEAR") # z
                length_frames = max([length_frames, keyframe])
        
        bpy.ops.screen.animation_cancel(restore_frame=False)        
        bpy.ops.screen.animation_play()
        context.scene.frame_end = length_frames + 1
        context.scene.frame_start = 0
        context.scene.render.fps = 30
        bpy.ops.object.mode_set(mode="POSE")

