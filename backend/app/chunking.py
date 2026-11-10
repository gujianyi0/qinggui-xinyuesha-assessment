"""Bound source text before embedding; offsets refer to extracted document text."""
CHUNK_SIZE = 320
CHUNK_OVERLAP = 64


def chunk_documents(documents: list[dict], size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("分块大小和重叠不合法")
    chunks = []
    for document in documents:
        text = document["text"]
        if len(text) <= size:
            chunks.append(document)
            continue
        start = index = 0
        while start < len(text):
            end = min(start + size, len(text))
            source = dict(document["source"])
            source.update(
                id=f"{source['id']}:chunk:{index}", parent_source_id=source["id"],
                parent_document_id=document["id"], char_start=start, char_end=end,
                excerpt=text[start:end],
            )
            chunks.append({**document, "id": f"{document['id']}:chunk:{index}", "text": text[start:end], "source": source})
            if end == len(text):
                break
            start, index = end - overlap, index + 1
    return chunks
