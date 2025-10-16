
class StingrayStateMachine:
    # very complicated, only load the animation IDs from the state machine for now
    
    def __init__(self):
        self.animation_ids = set()
        
    def load(self, memory_stream):
        offset_start = memory_stream.tell()
        temp = 0
        unk = memory_stream.uint32(temp)
        count = memory_stream.uint32(temp)
        initial_animation_group_offset = memory_stream.uint32(temp)
        memory_stream.seek(offset_start + initial_animation_group_offset)
        count = memory_stream.uint32(temp)
        animation_group_offsets = [memory_stream.uint32(t) for t in range(count)]
        for offset in animation_group_offsets:
            group_offset = offset_start + initial_animation_group_offset + offset
            memory_stream.seek(group_offset + 8)
            num_animations = memory_stream.uint32(temp)
            animation_offsets = [memory_stream.uint32(t) for t in range(num_animations)]
            for a_offset in animation_offsets:
                memory_stream.seek(group_offset + a_offset + 12)
                hash_count = memory_stream.uint32(temp)
                hash_offset = memory_stream.uint32(temp)
                memory_stream.seek(group_offset + a_offset + hash_offset)
                for _ in range(hash_count):
                    self.animation_ids.add(memory_stream.uint64(temp))

    def save(self, memory_stream):
        pass
        
    def Serialize(self, memory_stream):
        if memory_stream.IsReading():
            self.load(memory_stream)
        else:
            self.save(memory_stream)