import json
from typing import Union, Dict, Any

# Try importing google.cloud.storage
try:
    from google.cloud import storage
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False


def save_garment_metadata(gs_uri: str, metadata: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """
    Attaches structured garment metadata directly to a GCS Blob's custom metadata.
    Handles type conversion (lists/booleans/ints -> strings) required by GCS.
    """
    # 1. Normalize metadata input
    if isinstance(metadata, str):
        metadata_dict = json.loads(metadata)
    else:
        metadata_dict = dict(metadata)

    # 2. Parse GCS URI (gs://bucket_name/path/to/file.jpg)
    clean_uri = gs_uri.replace("gs://", "")
    parts = clean_uri.split("/", 1)
    if len(parts) != 2:
        return {"status": "error", "message": f"Invalid GCS URI provided: {gs_uri}"}
    
    bucket_name, blob_name = parts[0], parts[1]

    # 3. Format metadata
    formatted_metadata = {}
    for key, value in metadata_dict.items():
        if value is None:
            continue
        elif isinstance(value, list):
            formatted_metadata[key] = ", ".join(map(str, value))
        elif isinstance(value, bool):
            formatted_metadata[key] = "true" if value else "false"
        else:
            formatted_metadata[key] = str(value)

    if STORAGE_AVAILABLE:
        try:
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.get_blob(blob_name)
            if blob:
                blob.metadata = formatted_metadata
                blob.patch()
        except Exception as e:
            print(f"[StorageTool] GCS metadata patch skipped ({e}).")

    return {
        "status": "success",
        "gs_uri": gs_uri,
        "attached_metadata_keys": list(formatted_metadata.keys())
    }