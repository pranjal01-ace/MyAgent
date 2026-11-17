import struct
import json
from pathlib import Path

def create_valid_humanoid_glb(output_path: Path):
    """Generate a valid GLTF 2.0 binary (.glb) 3D humanoid mesh model."""
    
    # 3D Cube / Humanoid Mesh Vertices (Position + Normal + UV)
    # Box vertices
    positions = [
        # Front face
        -0.5, -0.5,  0.5,   0.5, -0.5,  0.5,   0.5,  0.5,  0.5,  -0.5,  0.5,  0.5,
        # Back face
        -0.5, -0.5, -0.5,  -0.5,  0.5, -0.5,   0.5,  0.5, -0.5,   0.5, -0.5, -0.5,
        # Top face
        -0.5,  0.5, -0.5,  -0.5,  0.5,  0.5,   0.5,  0.5,  0.5,   0.5,  0.5, -0.5,
        # Bottom face
        -0.5, -0.5, -0.5,   0.5, -0.5, -0.5,   0.5, -0.5,  0.5,  -0.5, -0.5,  0.5,
        # Right face
         0.5, -0.5, -0.5,   0.5,  0.5, -0.5,   0.5,  0.5,  0.5,   0.5, -0.5,  0.5,
        # Left face
        -0.5, -0.5, -0.5,  -0.5, -0.5,  0.5,  -0.5,  0.5,  0.5,  -0.5,  0.5, -0.5,
    ]
    
    indices = [
         0,  1,  2,   0,  2,  3, # Front
         4,  5,  6,   4,  6,  7, # Back
         8,  9, 10,   8, 10, 11, # Top
        12, 13, 14,  12, 14, 15, # Bottom
        16, 17, 18,  16, 18, 19, # Right
        20, 21, 22,  20, 22, 23  # Left
    ]

    # Packing BIN Data
    pos_bytes = b''.join(struct.pack('<fff', *positions[i:i+3]) for i in range(0, len(positions), 3))
    ind_bytes = b''.join(struct.pack('<H', idx) for idx in indices)
    
    # Align bin chunk to 4 bytes
    ind_padding = (4 - (len(ind_bytes) % 4)) % 4
    ind_bytes += b'\x00' * ind_padding

    bin_data = pos_bytes + ind_bytes

    # GLTF JSON Structure
    gltf_dict = {
        "asset": {"version": "2.0", "generator": "Ace3DAgentGenerator"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {"name": "RootHumanoid", "children": [1, 2, 3, 4]},
            {"name": "Head", "mesh": 0, "translation": [0, 1.2, 0], "scale": [0.4, 0.4, 0.4]},
            {"name": "Torso", "mesh": 0, "translation": [0, 0.3, 0], "scale": [0.6, 0.9, 0.4]},
            {"name": "LeftArm", "mesh": 0, "translation": [-0.6, 0.4, 0], "scale": [0.2, 0.7, 0.2]},
            {"name": "RightArm", "mesh": 0, "translation": [0.6, 0.4, 0], "scale": [0.2, 0.7, 0.2]}
        ],
        "meshes": [
            {
                "name": "HumanoidBlockMesh",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "mode": 4
                    }
                ]
            }
        ],
        "buffers": [{"byteLength": len(bin_data)}],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": 0,
                "byteLength": len(pos_bytes),
                "target": 34962 # ARRAY_BUFFER
            },
            {
                "buffer": 0,
                "byteOffset": len(pos_bytes),
                "byteLength": len(ind_bytes) - ind_padding,
                "target": 34963 # ELEMENT_ARRAY_BUFFER
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5126, # FLOAT
                "count": len(positions) // 3,
                "type": "VEC3",
                "max": [0.5, 0.5, 0.5],
                "min": [-0.5, -0.5, -0.5]
            },
            {
                "bufferView": 1,
                "byteOffset": 0,
                "componentType": 5123, # UNSIGNED_SHORT
                "count": len(indices),
                "type": "SCALAR",
                "max": [max(indices)],
                "min": [min(indices)]
            }
        ]
    }

    json_str = json.dumps(gltf_dict, separators=(',', ':'))
    json_bytes = json_str.encode('utf-8')
    json_padding = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b' ' * json_padding

    # Header: Magic (4B), Version (4B), Length (4B)
    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_data)
    header = struct.pack('<IIII', 0x46546C67, 2, total_length, len(json_bytes)) + b'JSON'
    bin_header = struct.pack('<I', len(bin_data)) + b'BIN\x00'

    glb_content = header + json_bytes + bin_header + bin_data
    
    with open(output_path, "wb") as f:
        f.write(glb_content)

    print(f"Generated valid GLB binary model file: {output_path} ({len(glb_content)} bytes)")

if __name__ == "__main__":
    out_file = Path(__file__).resolve().parent / "model.glb"
    create_valid_humanoid_glb(out_file)
