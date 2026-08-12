from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_documents(documents):
    """Chunk the uploaded resume - identical settings to the Streamlit app so retrieval
    quality/behavior stays consistent between both apps."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=100,
        separators=["\n\n", "\n", "•", "-", " ", ""],
    )
    splits = text_splitter.split_documents(documents)

    enhanced = []
    for split in splits:
        content = split.page_content
        if "experience" in content.lower() or "worked" in content.lower():
            content = "[EXPERIENCE]\n" + content
        split.page_content = content
        enhanced.append(split)
    return enhanced
