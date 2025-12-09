
class StingrayStateMachine:
    # very complicated, only load the animation IDs from the state machine for now
    
    def __init__(self):
        self.animation_ids = set()
        self.layer_count = self.layer_data_offset = self.animation_events_count = self.animation_events_offset = self.animation_vars_count = self.animation_vars_offset = 0
        self.blend_mask_count = self.blend_mask_offset = 0
        self.layers = []
        self.blend_masks = []
        
    def load(self, memory_stream):
        offset_start = memory_stream.tell()
        temp = 0
        unk = memory_stream.uint32(temp)
        self.layer_count = memory_stream.uint32(self.layer_count)
        self.layer_data_offset = memory_stream.uint32(self.layer_data_offset)
        self.animation_events_count = memory_stream.uint32(self.animation_events_count)
        self.animation_events_offset = memory_stream.uint32(self.animation_events_offset)
        self.animation_vars_count = memory_stream.uint32(self.animation_vars_count)
        self.animation_vars_offset = memory_stream.uint32(self.animation_vars_offset)
        self.blend_mask_count = memory_stream.uint32(self.blend_mask_count)
        self.blend_mask_offset = memory_stream.uint32(self.blend_mask_offset)
        
        # get layers
        memory_stream.seek(offset_start + self.layer_data_offset)
        self.layer_count = memory_stream.uint32(self.layer_count)
        layer_offsets = [memory_stream.uint32(t) for t in range(self.layer_count)]
        for offset in layer_offsets:
            layer_offset = offset_start + self.layer_data_offset + offset
            memory_stream.seek(layer_offset)
            new_layer = Layer()
            new_layer.load(memory_stream)
            self.layers.append(new_layer)
            
        # get blend masks
        memory_stream.seek(offset_start + self.blend_mask_offset)
        self.blend_mask_count = memory_stream.uint32(self.blend_mask_count)
        print(f"Num blend masks:{self.blend_mask_count}")
        blend_mask_offsets = [memory_stream.uint32(t) for t in range(self.blend_mask_count)]
        for offset in blend_mask_offsets:
            memory_stream.seek(offset_start + self.blend_mask_offset + offset)
            new_blend_mask = BlendMask()
            new_blend_mask.load(memory_stream)
            self.blend_masks.append(new_blend_mask)
            
        for layer in self.layers:
            for state in layer.states:
                for animation_id in state.animation_ids:
                    self.animation_ids.add(animation_id)

    def save(self, memory_stream):
        pass
        
    def Serialize(self, memory_stream):
        if memory_stream.IsReading():
            self.load(memory_stream)
        else:
            self.save(memory_stream)
            
class Layer:
    
    def __init__(self):
        self.magic = self.default_state = self.num_states = 0
        self.state_offsets = []
        self.states = []
    
    def load(self, memory_stream):
        offset_start = memory_stream.tell()
        self.magic = memory_stream.uint32(self.magic)
        self.default_state = memory_stream.uint32(self.default_state)
        self.num_states = memory_stream.uint32(self.num_states)
        self.state_offsets = [memory_stream.uint32(t) for t in range(self.num_states)]
        for state_offset in self.state_offsets:
            memory_stream.seek(offset_start + state_offset)
            new_state = State()
            new_state.load(memory_stream)
            self.states.append(new_state)
    
class State:
    
    def __init__(self):
        self.name = self.state_type = self.animation_count = self.animation_offset = self.blend_mask_index = 0
        self.animation_ids = []
    
    def load(self, stream):
        offset_start = stream.tell()
        self.name = stream.uint64(self.name)
        self.state_type = stream.uint32(self.state_type)
        self.animation_count = stream.uint32(self.animation_count)
        self.animation_offset = stream.uint32(self.animation_offset)
        
        stream.seek(stream.tell() + 88) # skip all that other stuff for now
        self.blend_mask_index = stream.uint32(self.blend_mask_index) # I assume 0xFFFFFFFF means no mask
        
        stream.seek(offset_start + self.animation_offset)
        self.animation_ids = [stream.uint64(t) for t in range(self.animation_count)]
    
class BlendMask:
    
    def __init__(self):
        self.bone_count = 0
        self.bone_weights = []
        
    def load(self, stream):
        self.bone_count = stream.uint32(self.bone_count)
        print(self.bone_count)
        print(stream.tell())
        self.bone_weights = [stream.float32(t) for t in range(self.bone_count)]