import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

const BRAND = {
    emerald: [16, 185, 129] as const,
    darkBg: [6, 9, 15] as const,
    heading: [226, 232, 240] as const,

    pdfBg: [255, 255, 255] as const,
    pdfText: [31, 41, 55] as const,
    pdfHeading: [17, 24, 39] as const,
    pdfMuted: [107, 114, 128] as const,
    pdfBorder: [229, 231, 235] as const,
    pdfTableHead: [16, 185, 129] as const,
    pdfTableHeadText: [255, 255, 255] as const,
    pdfSuccess: [16, 185, 129] as const,
    pdfWarning: [245, 158, 11] as const,
    pdfDanger: [239, 68, 68] as const,
};

type SectionColor = 'success' | 'warning' | 'danger' | 'neutral';

export interface PDFSection {
    type: 'heading' | 'text' | 'table' | 'keyValue' | 'spacer' | 'divider' | 'badge' | 'statusBadge';
    text?: string;
    level?: 1 | 2 | 3;
    body?: string;
    headers?: string[];
    rows?: string[][];
    pairs?: { key: string; value: string; status?: SectionColor }[];
    label?: string;
    color?: SectionColor;
}

export interface PDFReportConfig {
    title: string;
    subtitle?: string;
    reportType?: string;
    generatedAt?: Date;
    sections: PDFSection[];
    footer?: {
        left?: string;
        right?: string;
        legalLine?: string;
    };
    filename: string;
}

type DocWithAutoTable = jsPDF & {
    lastAutoTable?: {
        finalY: number;
    };
};

const HORIZONTAL_MARGIN = 20;
const CONTENT_TOP = 30;
const FOOTER_RESERVED = 24;

function getStatusColor(color: SectionColor = 'neutral'): readonly [number, number, number] {
    switch (color) {
        case 'success':
            return BRAND.pdfSuccess;
        case 'warning':
            return BRAND.pdfWarning;
        case 'danger':
            return BRAND.pdfDanger;
        default:
            return BRAND.pdfMuted;
    }
}

function drawHeader(doc: jsPDF, pageWidth: number, generatedLabel: string, reportType: string): void {
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(8);
    doc.setTextColor(...BRAND.emerald);
    doc.text('REGENGINE', HORIZONTAL_MARGIN, 10);

    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...BRAND.pdfMuted);
    doc.text(generatedLabel, pageWidth - HORIZONTAL_MARGIN, 10, { align: 'right' });

    doc.setDrawColor(...BRAND.emerald);
    doc.setLineWidth(0.7);
    doc.line(HORIZONTAL_MARGIN, 13, pageWidth - HORIZONTAL_MARGIN, 13);

    doc.setFontSize(9);
    doc.setTextColor(...BRAND.pdfMuted);
    doc.text(reportType, HORIZONTAL_MARGIN, 18);
}

function drawFooter(
    doc: jsPDF,
    pageWidth: number,
    pageHeight: number,
    pageNumber: number,
    totalPages: number,
    footer: PDFReportConfig['footer'],
): void {
    const left = footer?.left || 'Confidential';
    const right = footer?.right || 'regengine.co';
    const legalLine = footer?.legalLine || '';

    const primaryY = pageHeight - 10;
    const legalY = pageHeight - 5;

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor(...BRAND.pdfMuted);

    doc.text(left, HORIZONTAL_MARGIN, primaryY);
    doc.text(`Page ${pageNumber} of ${totalPages}`, pageWidth / 2, primaryY, { align: 'center' });
    doc.text(right, pageWidth - HORIZONTAL_MARGIN, primaryY, { align: 'right' });

    if (legalLine) {
        doc.text(legalLine, pageWidth / 2, legalY, { align: 'center' });
    }
}

export function generateBrandedPDF(config: PDFReportConfig): void {
    const doc = new jsPDF();
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const contentMaxY = pageHeight - FOOTER_RESERVED;
    const generatedAt = config.generatedAt || new Date();
    const generatedLabel = `Generated: ${generatedAt.toLocaleString()}`;
    const reportType = config.reportType || 'Compliance Report';
    const contentWidth = pageWidth - HORIZONTAL_MARGIN * 2;

    let yPosition = CONTENT_TOP;

    const ensureSpace = (requiredHeight: number) => {
        if (yPosition + requiredHeight > contentMaxY) {
            doc.addPage();
            yPosition = CONTENT_TOP;
        }
    };

    const writeWrapped = (
        text: string,
        options: {
            x?: number;
            maxWidth?: number;
            fontSize?: number;
            bold?: boolean;
            color?: readonly [number, number, number];
            lineHeight?: number;
            spacingAfter?: number;
        } = {},
    ) => {
        if (!text) return;

        const x = options.x ?? HORIZONTAL_MARGIN;
        const maxWidth = options.maxWidth ?? contentWidth;
        const fontSize = options.fontSize ?? 10;
        const bold = options.bold ?? false;
        const color = options.color ?? BRAND.pdfText;

        doc.setFont('helvetica', bold ? 'bold' : 'normal');
        doc.setFontSize(fontSize);
        doc.setTextColor(...color);

        const lines = doc.splitTextToSize(text, maxWidth) as string[];
        const computedLineHeight = options.lineHeight ?? doc.getTextDimensions('Mg').h * 1.25;
        const blockHeight = lines.length * computedLineHeight;
        const spacingAfter = options.spacingAfter ?? 1.5;

        ensureSpace(blockHeight + spacingAfter);
        doc.text(lines, x, yPosition);
        yPosition += blockHeight + spacingAfter;
    };

    const drawBadge = (label: string, color: SectionColor = 'neutral') => {
        if (!label) return;
        const fill = getStatusColor(color);

        doc.setFont('helvetica', 'bold');
        doc.setFontSize(8);

        const badgeTextWidth = doc.getTextWidth(label);
        const badgeWidth = Math.max(20, badgeTextWidth + 8);
        const badgeHeight = 6;

        ensureSpace(badgeHeight + 2);
        doc.setFillColor(...fill);
        doc.roundedRect(HORIZONTAL_MARGIN, yPosition - 4.5, badgeWidth, badgeHeight, 1.5, 1.5, 'F');

        doc.setTextColor(...BRAND.pdfTableHeadText);
        doc.text(label, HORIZONTAL_MARGIN + 4, yPosition - 0.6);
        yPosition += 4.5;
    };

    // Title block (first page only)
    writeWrapped(config.title, {
        fontSize: 20,
        bold: true,
        color: BRAND.pdfHeading,
        lineHeight: 7,
        spacingAfter: 2,
    });

    if (config.subtitle) {
        writeWrapped(config.subtitle, {
            fontSize: 12,
            color: BRAND.pdfMuted,
            lineHeight: 5,
            spacingAfter: 4,
        });
    } else {
        yPosition += 2;
    }

    for (const section of config.sections) {
        switch (section.type) {
            case 'heading': {
                const text = section.text || '';
                if (!text) break;

                const level = section.level ?? 2;
                const sizeByLevel: Record<1 | 2 | 3, number> = {
                    1: 16,
                    2: 14,
                    3: 12,
                };

                yPosition += 1;
                writeWrapped(text, {
                    fontSize: sizeByLevel[level],
                    bold: true,
                    color: BRAND.pdfHeading,
                    lineHeight: doc.getTextDimensions('Mg').h * 1.2,
                    spacingAfter: 2,
                });
                break;
            }

            case 'text': {
                const body = section.body || '';
                if (!body) break;

                const paragraphs = body.split('\n');
                paragraphs.forEach((paragraph, index) => {
                    const paragraphText = paragraph.trim() ? paragraph : ' ';
                    writeWrapped(paragraphText, {
                        fontSize: 10,
                        color: BRAND.pdfText,
                        lineHeight: 4.8,
                        spacingAfter: index < paragraphs.length - 1 ? 1 : 2,
                    });
                });
                break;
            }

            case 'table': {
                const headers = section.headers || [];
                const rows = section.rows || [];
                if (headers.length === 0) break;

                ensureSpace(12);
                autoTable(doc, {
                    startY: yPosition,
                    head: [headers],
                    body: rows,
                    theme: 'striped',
                    headStyles: {
                        fillColor: [...BRAND.pdfTableHead],
                        textColor: [...BRAND.pdfTableHeadText],
                        fontStyle: 'bold',
                        fontSize: 9,
                    },
                    bodyStyles: {
                        fontSize: 9,
                        textColor: [...BRAND.pdfText],
                    },
                    alternateRowStyles: {
                        fillColor: [249, 250, 251],
                    },
                    styles: {
                        font: 'helvetica',
                        lineColor: [...BRAND.pdfBorder],
                        lineWidth: 0.1,
                        cellPadding: 2,
                    },
                    margin: { left: HORIZONTAL_MARGIN, right: HORIZONTAL_MARGIN, bottom: FOOTER_RESERVED },
                });

                const withTable = doc as DocWithAutoTable;
                yPosition = (withTable.lastAutoTable?.finalY ?? yPosition) + 5;
                break;
            }

            case 'keyValue': {
                const pairs = section.pairs || [];
                if (pairs.length === 0) break;

                const keyWidth = 56;
                const keyX = HORIZONTAL_MARGIN;
                const valueX = keyX + keyWidth + 8;
                const valueWidth = pageWidth - HORIZONTAL_MARGIN - valueX;

                for (const pair of pairs) {
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(10);
                    const keyLines = doc.splitTextToSize(pair.key, keyWidth) as string[];

                    doc.setFont('helvetica', 'normal');
                    const valueLines = doc.splitTextToSize(pair.value, valueWidth) as string[];

                    const rowLines = Math.max(keyLines.length, valueLines.length);
                    const rowHeight = rowLines * 4.6 + 1.2;
                    ensureSpace(rowHeight + 1);

                    if (pair.status && pair.status !== 'neutral') {
                        doc.setFillColor(...getStatusColor(pair.status));
                        doc.circle(valueX - 4, yPosition - 1.2, 1, 'F');
                    }

                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(10);
                    doc.setTextColor(...BRAND.pdfHeading);
                    doc.text(keyLines, keyX, yPosition);

                    doc.setFont('helvetica', 'normal');
                    doc.setTextColor(...BRAND.pdfText);
                    doc.text(valueLines, valueX, yPosition);

                    yPosition += rowHeight;
                }

                yPosition += 1;
                break;
            }

            case 'spacer': {
                yPosition += 4;
                break;
            }

            case 'divider': {
                ensureSpace(4);
                doc.setDrawColor(...BRAND.pdfBorder);
                doc.setLineWidth(0.25);
                doc.line(HORIZONTAL_MARGIN, yPosition, pageWidth - HORIZONTAL_MARGIN, yPosition);
                yPosition += 4;
                break;
            }

            case 'badge': {
                if (section.label) {
                    drawBadge(section.label, section.color || 'neutral');
                }
                break;
            }

            case 'statusBadge': {
                if (section.label) {
                    drawBadge(section.label, section.color || 'neutral');
                }
                break;
            }

            default:
                break;
        }
    }

    const totalPages = doc.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
        doc.setPage(i);
        drawHeader(doc, pageWidth, generatedLabel, reportType);
        drawFooter(doc, pageWidth, pageHeight, i, totalPages, config.footer);
    }

    doc.save(`${config.filename}.pdf`);
}
