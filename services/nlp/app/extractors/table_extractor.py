"""
Table Extractor using Microsoft Table Transformer for layout-aware extraction.

Provides structured table detection and row-level cell extraction from documents.
"""

import io
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import structlog

if TYPE_CHECKING:
    from PIL import Image

logger = structlog.get_logger("table-extractor")

# Lazy imports for heavy dependencies
_TORCH_AVAILABLE = None
_TRANSFORMERS_AVAILABLE = None
_PIL_AVAILABLE = None
_PDF2IMAGE_AVAILABLE = None
_PDFPLUMBER_AVAILABLE = None


def _check_dependencies():
    """Check and cache availability of optional dependencies."""
    global _TORCH_AVAILABLE, _TRANSFORMERS_AVAILABLE, _PIL_AVAILABLE
    global _PDF2IMAGE_AVAILABLE, _PDFPLUMBER_AVAILABLE

    if _TORCH_AVAILABLE is None:
        try:
            import torch

            _TORCH_AVAILABLE = True
        except ImportError:
            _TORCH_AVAILABLE = False

    if _TRANSFORMERS_AVAILABLE is None:
        try:
            from transformers import AutoImageProcessor, AutoModelForObjectDetection

            _TRANSFORMERS_AVAILABLE = True
        except ImportError:
            _TRANSFORMERS_AVAILABLE = False

    if _PIL_AVAILABLE is None:
        try:
            from PIL import Image

            _PIL_AVAILABLE = True
        except ImportError:
            _PIL_AVAILABLE = False

    if _PDF2IMAGE_AVAILABLE is None:
        try:
            from pdf2image import convert_from_bytes

            _PDF2IMAGE_AVAILABLE = True
        except ImportError:
            _PDF2IMAGE_AVAILABLE = False

    if _PDFPLUMBER_AVAILABLE is None:
        try:
            import pdfplumber

            _PDFPLUMBER_AVAILABLE = True
        except ImportError:
            _PDFPLUMBER_AVAILABLE = False


@dataclass
class BoundingBox:
    """Bounding box coordinates (normalized 0-1 or pixel-based)."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
        }

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is within this bounding box."""
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max

    def overlaps(self, other: "BoundingBox", threshold: float = 0.5) -> bool:
        """Check if this box overlaps with another by given threshold."""
        x_overlap = max(0, min(self.x_max, other.x_max) - max(self.x_min, other.x_min))
        y_overlap = max(0, min(self.y_max, other.y_max) - max(self.y_min, other.y_min))

        intersection = x_overlap * y_overlap
        self_area = (self.x_max - self.x_min) * (self.y_max - self.y_min)

        if self_area == 0:
            return False

        return (intersection / self_area) >= threshold


@dataclass
class TableCell:
    """A single cell in a detected table."""

    text: str
    row_index: int
    col_index: int
    bounding_box: Optional[BoundingBox] = None
    confidence: float = 1.0


@dataclass
class TableRow:
    """A row in a detected table with ordered cells."""

    row_index: int
    cells: List[TableCell] = field(default_factory=list)
    bounding_box: Optional[BoundingBox] = None

    @property
    def text(self) -> str:
        """Concatenate all cell text in this row."""
        return " ".join(c.text for c in self.cells if c.text)


@dataclass
class DetectedTable:
    """A table detected in a document page."""

    page_number: int
    rows: List[TableRow] = field(default_factory=list)
    bounding_box: Optional[BoundingBox] = None
    confidence: float = 1.0

    @property
    def headers(self) -> Optional[TableRow]:
        """Return the first row as headers."""
        return self.rows[0] if self.rows else None


class TableExtractor:
    """
    Layout-aware table extractor using Microsoft Table Transformer (TATR).

    Uses two models:
    - Table Detection: microsoft/table-transformer-detection
    - Structure Recognition: microsoft/table-transformer-structure-recognition

    Falls back to pdfplumber for text-based table extraction when:
    - Deep learning models are unavailable
    - Document is text-based PDF (not scanned)
    - Confidence is low on model detection
    """

    # Model identifiers
    DETECTION_MODEL = "microsoft/table-transformer-detection"
    STRUCTURE_MODEL = "microsoft/table-transformer-structure-recognition"

    # Detection thresholds
    TABLE_CONFIDENCE_THRESHOLD = 0.7
    CELL_CONFIDENCE_THRESHOLD = 0.5

    def __init__(
        self,
        device: Optional[str] = None,
        use_gpu: bool = True,
        cache_dir: Optional[str] = None,
    ):
        """
        Initialize the table extractor.

        Args:
            device: Force specific device ('cpu', 'cuda', 'mps')
            use_gpu: Whether to attempt GPU usage (auto-detect)
            cache_dir: Directory for caching models
        """
        _check_dependencies()

        self.device = device
        self.use_gpu = use_gpu
        self.cache_dir = cache_dir or os.getenv("HF_HOME", "~/.cache/huggingface")

        # Lazy-loaded models
        self._detection_model = None
        self._detection_processor = None
        self._structure_model = None
        self._structure_processor = None

        # Determine device
        if self.device is None:
            self.device = self._auto_detect_device()

        logger.info(
            "table_extractor_initialized",
            device=self.device,
            torch_available=_TORCH_AVAILABLE,
            transformers_available=_TRANSFORMERS_AVAILABLE,
        )

    def _auto_detect_device(self) -> str:
        """Auto-detect the best available device."""
        if not _TORCH_AVAILABLE or not self.use_gpu:
            return "cpu"

        import torch

        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"  # Apple Silicon

        return "cpu"

    def _load_detection_model(self):
        """Lazy-load the table detection model."""
        if self._detection_model is not None:
            return

        if not _TRANSFORMERS_AVAILABLE or not _TORCH_AVAILABLE:
            logger.warning("transformers_or_torch_unavailable", fallback="pdfplumber")
            return

        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        logger.info("loading_detection_model", model=self.DETECTION_MODEL)

        self._detection_processor = AutoImageProcessor.from_pretrained(
            self.DETECTION_MODEL,
            cache_dir=self.cache_dir,
        )
        self._detection_model = AutoModelForObjectDetection.from_pretrained(
            self.DETECTION_MODEL,
            cache_dir=self.cache_dir,
        )
        self._detection_model.to(self.device)
        self._detection_model.eval()

        logger.info("detection_model_loaded", device=self.device)

    def _load_structure_model(self):
        """Lazy-load the table structure recognition model."""
        if self._structure_model is not None:
            return

        if not _TRANSFORMERS_AVAILABLE or not _TORCH_AVAILABLE:
            logger.warning("transformers_or_torch_unavailable", fallback="pdfplumber")
            return

        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        logger.info("loading_structure_model", model=self.STRUCTURE_MODEL)

        self._structure_processor = AutoImageProcessor.from_pretrained(
            self.STRUCTURE_MODEL,
            cache_dir=self.cache_dir,
        )
        self._structure_model = AutoModelForObjectDetection.from_pretrained(
            self.STRUCTURE_MODEL,
            cache_dir=self.cache_dir,
        )
        self._structure_model.to(self.device)
        self._structure_model.eval()

        logger.info("structure_model_loaded", device=self.device)

    def extract_tables_from_pdf(
        self,
        pdf_bytes: bytes,
        pages: Optional[List[int]] = None,
    ) -> List[DetectedTable]:
        """
        Extract tables from a PDF document.

        Args:
            pdf_bytes: Raw PDF file content
            pages: Specific pages to process (1-indexed), None for all

        Returns:
            List of detected tables with rows and cells
        """
        # Try deep learning approach first
        if _TORCH_AVAILABLE and _TRANSFORMERS_AVAILABLE and _PDF2IMAGE_AVAILABLE:
            tables = self._extract_tables_dl(pdf_bytes, pages)
            if tables:
                return tables

        # Fall back to pdfplumber
        if _PDFPLUMBER_AVAILABLE:
            return self._extract_tables_pdfplumber(pdf_bytes, pages)

        logger.error("no_table_extraction_available")
        return []

    def _extract_tables_dl(
        self,
        pdf_bytes: bytes,
        pages: Optional[List[int]] = None,
    ) -> List[DetectedTable]:
        """Extract tables using Table Transformer deep learning models."""
        import torch
        from pdf2image import convert_from_bytes
        from PIL import Image

        self._load_detection_model()
        self._load_structure_model()

        if self._detection_model is None:
            return []

        # Convert PDF to images
        try:
            images = convert_from_bytes(pdf_bytes, dpi=200)
        except Exception as e:
            logger.error("pdf_to_image_failed", error=str(e))
            return []

        all_tables = []

        for page_idx, page_image in enumerate(images):
            page_num = page_idx + 1

            # Skip if specific pages requested and this isn't one
            if pages and page_num not in pages:
                continue

            # Detect tables on this page
            detected = self._detect_tables_on_image(page_image, page_num)

            for table_bbox, table_conf in detected:
                if table_conf < self.TABLE_CONFIDENCE_THRESHOLD:
                    continue

                # Crop table region
                table_image = page_image.crop(
                    (
                        int(table_bbox.x_min),
                        int(table_bbox.y_min),
                        int(table_bbox.x_max),
                        int(table_bbox.y_max),
                    )
                )

                # Extract structure
                rows = self._extract_table_structure(table_image, page_image)

                table = DetectedTable(
                    page_number=page_num,
                    rows=rows,
                    bounding_box=table_bbox,
                    confidence=table_conf,
                )
                all_tables.append(table)

        logger.info("tables_extracted_dl", count=len(all_tables))
        return all_tables

    def _detect_tables_on_image(
        self,
        image: "Image.Image",
        page_num: int,
    ) -> List[Tuple[BoundingBox, float]]:
        """Detect table bounding boxes on a page image."""
        import torch

        inputs = self._detection_processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._detection_model(**inputs)

        # Post-process detections
        target_sizes = torch.tensor([image.size[::-1]]).to(self.device)
        results = self._detection_processor.post_process_object_detection(
            outputs,
            threshold=self.TABLE_CONFIDENCE_THRESHOLD,
            target_sizes=target_sizes,
        )[0]

        detections = []
        for score, label, box in zip(
            results["scores"], results["labels"], results["boxes"]
        ):
            # Label 0 is typically "table" in table-transformer
            if label.item() == 0:
                bbox = BoundingBox(
                    x_min=box[0].item(),
                    y_min=box[1].item(),
                    x_max=box[2].item(),
                    y_max=box[3].item(),
                )
                detections.append((bbox, score.item()))

        logger.debug("tables_detected", page=page_num, count=len(detections))
        return detections

    def _extract_table_structure(
        self,
        table_image: "Image.Image",
        full_page_image: "Image.Image",
    ) -> List[TableRow]:
        """Extract row/cell structure from a table image."""
        import torch

        inputs = self._structure_processor(images=table_image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._structure_model(**inputs)

        target_sizes = torch.tensor([table_image.size[::-1]]).to(self.device)
        results = self._structure_processor.post_process_object_detection(
            outputs,
            threshold=self.CELL_CONFIDENCE_THRESHOLD,
            target_sizes=target_sizes,
        )[0]

        # Group by rows (labels: 0=table, 1=table column, 2=table row,
        #                       3=table column header, 4=table projected row header, 5=table spanning cell)
        row_boxes = []
        cell_boxes = []

        for score, label, box in zip(
            results["scores"], results["labels"], results["boxes"]
        ):
            bbox = BoundingBox(
                x_min=box[0].item(),
                y_min=box[1].item(),
                x_max=box[2].item(),
                y_max=box[3].item(),
            )

            label_id = label.item()
            if label_id == 2:  # table row
                row_boxes.append((bbox, score.item()))
            # Note: Cell detection may need additional processing
            # For now we rely on row detection + text extraction

        # Sort rows by y-position (top to bottom)
        row_boxes.sort(key=lambda x: x[0].y_min)

        rows = []
        for row_idx, (row_bbox, row_conf) in enumerate(row_boxes):
            row = TableRow(
                row_index=row_idx,
                bounding_box=row_bbox,
                cells=[],  # Cells will be populated by text extraction
            )
            rows.append(row)

        return rows

    def _extract_tables_pdfplumber(
        self,
        pdf_bytes: bytes,
        pages: Optional[List[int]] = None,
    ) -> List[DetectedTable]:
        """Fallback table extraction using pdfplumber."""
        import pdfplumber

        all_tables = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1

                if pages and page_num not in pages:
                    continue

                # Extract tables from this page
                tables = page.extract_tables()

                for table_data in tables:
                    if not table_data:
                        continue

                    rows = []
                    for row_idx, row_data in enumerate(table_data):
                        cells = []
                        for col_idx, cell_text in enumerate(row_data):
                            cell = TableCell(
                                text=cell_text or "",
                                row_index=row_idx,
                                col_index=col_idx,
                            )
                            cells.append(cell)

                        row = TableRow(row_index=row_idx, cells=cells)
                        rows.append(row)

                    table = DetectedTable(
                        page_number=page_num,
                        rows=rows,
                        confidence=0.9,  # pdfplumber is reliable for text PDFs
                    )
                    all_tables.append(table)

        logger.info("tables_extracted_pdfplumber", count=len(all_tables))
        return all_tables

    def extract_tables_from_text(
        self,
        text: str,
        delimiter_patterns: Optional[List[str]] = None,
    ) -> List[DetectedTable]:
        """
        Extract table-like structures from plain text.

        Uses heuristics to detect aligned columns and row separators.
        Useful for BOLs and invoices that are already OCR'd.

        Args:
            text: Plain text content
            delimiter_patterns: Regex patterns that indicate row boundaries

        Returns:
            List of detected tables
        """
        if delimiter_patterns is None:
            delimiter_patterns = [
                r"[-=]{3,}",  # Separator lines
                r"^\s*\d+\.\s+",  # Numbered items
                r"^\s*Item\s+",  # Item headers
            ]

        lines = text.split("\n")
        tables = []
        current_rows = []

        # Simple heuristic: look for aligned patterns
        for line_idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                # Empty line might indicate table boundary
                if len(current_rows) >= 2:
                    rows = [
                        TableRow(
                            row_index=i,
                            cells=[TableCell(text=r, row_index=i, col_index=0)],
                        )
                        for i, r in enumerate(current_rows)
                    ]
                    tables.append(
                        DetectedTable(page_number=1, rows=rows, confidence=0.6)
                    )
                current_rows = []
            else:
                # Check if line looks like table data (has tabs or consistent spacing)
                if "\t" in line or self._looks_like_table_row(line):
                    current_rows.append(stripped)

        # Handle remaining rows
        if len(current_rows) >= 2:
            rows = [
                TableRow(
                    row_index=i,
                    cells=[TableCell(text=r, row_index=i, col_index=0)],
                )
                for i, r in enumerate(current_rows)
            ]
            tables.append(DetectedTable(page_number=1, rows=rows, confidence=0.6))

        return tables

    def _looks_like_table_row(self, line: str) -> bool:
        """Heuristic to detect if a line looks like a table row."""
        import re

        # Multiple whitespace-separated groups
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 3:
            return True

        # Tab-separated
        if line.count("\t") >= 2:
            return True

        # Has quantity-like pattern followed by other content
        if re.search(r"\d+\s+(cases?|units?|lbs?|kg|ea)", line, re.IGNORECASE):
            return True

        return False
