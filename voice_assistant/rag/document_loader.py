import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("assistant.rag.loader")

class DocumentLoader:
    """Document loader supporting .txt, .md, .pdf, and .docx files."""

    @staticmethod
    def load_document(file_path: Path) -> List[Dict[str, Any]]:
        file_path = Path(file_path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return []

        ext = file_path.suffix.lower()
        if ext in [".txt", ".md"]:
            return DocumentLoader._load_text(file_path)
        elif ext == ".pdf":
            return DocumentLoader._load_pdf(file_path)
        elif ext == ".docx":
            return DocumentLoader._load_docx(file_path)
        else:
            logger.warning(f"Unsupported document format: {ext}")
            return []

    @staticmethod
    def _load_text(file_path: Path) -> List[Dict[str, Any]]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return [{
                "text": content,
                "metadata": {
                    "source": str(file_path),
                    "filename": file_path.name,
                    "page": 1
                }
            }]
        except Exception as e:
            logger.error(f"Error reading text file {file_path}: {e}")
            return []

    @staticmethod
    def _load_pdf(file_path: Path) -> List[Dict[str, Any]]:
        documents = []
        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    documents.append({
                        "text": text,
                        "metadata": {
                            "source": str(file_path),
                            "filename": file_path.name,
                            "page": i + 1
                        }
                    })
        except Exception as e:
            logger.error(f"Error reading PDF file {file_path}: {e}")
        return documents

    @staticmethod
    def _load_docx(file_path: Path) -> List[Dict[str, Any]]:
        try:
            import docx
            doc = docx.Document(str(file_path))
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            return [{
                "text": full_text,
                "metadata": {
                    "source": str(file_path),
                    "filename": file_path.name,
                    "page": 1
                }
            }]
        except Exception as e:
            logger.error(f"Error reading DOCX file {file_path}: {e}")
            return []
