// Label Types - FSMA 204 compliant food traceability labels

export interface LabelFormData {
    packerGln: string;
    gtin: string;
    productDescription: string;
    plu: string;
    expectedUnits: number;
    lotNumber: string;
    packDate: string;
    growerGln: string;
    quantity: number;
    unitOfMeasure: string;
    packagingLevel: string;
}

export interface LabelBatchInitRequest {
    lot_code: string;
    product_name: string;
    gtin?: string;
    quantity: number;
    facility_gln?: string;
    packer_gln?: string;
    harvest_date?: string;
    pack_date?: string;
    expiration_date?: string;
    origin_country?: string;
    grower_name?: string;
    product?: {
        gtin: string;
        description: string;
        plu?: string;
        expected_units?: number;
    };
    traceability?: {
        lot_number: string;
        pack_date: string;
        grower_gln?: string;
    };
    unit_of_measure?: string;
    packaging_level?: string;
    additional_data?: Record<string, unknown>;
}

export interface LabelBatchInitResponse {
    batch_id: string;
    lot_code: string;
    tlc?: string;  // Traceability Lot Code
    labels: GeneratedLabel[];
    reserved_range?: {
        start: string;
        end: string;
    };
    created_at: string;
    status: 'PENDING' | 'GENERATED' | 'PRINTED' | 'ERROR';
}

export interface GeneratedLabel {
    serial_number: string;
    serial?: string;        // alias for serial_number
    qr_code_data: string;
    qr_payload?: string;    // alias for qr_code_data
    barcode_data?: string;
    data_url?: string;
    zpl_code?: string;      // ZPL format for label printers
    verified: boolean;
}

export interface LabelData {
    serial: string;
    qr_payload: string;
    product_name: string;
    lot_code: string;
    pack_date: string;
    packer_gln: string;
    grower_gln?: string;
    packaging_level?: string;
}

export interface LabelTemplate {
    id: string;
    name: string;
    description?: string;
    format: 'PDF' | 'ZPL' | 'PNG';
    width_mm: number;
    height_mm: number;
    elements: LabelElement[];
}

export interface LabelElement {
    type: 'TEXT' | 'BARCODE' | 'QR_CODE' | 'IMAGE' | 'LINE';
    x: number;
    y: number;
    width?: number;
    height?: number;
    content?: string;
    font_size?: number;
    font_weight?: 'normal' | 'bold';
    align?: 'left' | 'center' | 'right';
}

export interface LabelPrintJob {
    id: string;
    batch_id: string;
    printer_id?: string;
    status: 'QUEUED' | 'PRINTING' | 'COMPLETED' | 'FAILED';
    labels_printed: number;
    labels_total: number;
    started_at?: string;
    completed_at?: string;
    error_message?: string;
}

export interface ScannedLabel {
    serial_number: string;
    lot_code: string;
    scan_timestamp: string;
    location?: string;
    scanner_id?: string;
    event_type: 'CREATED' | 'SHIPPED' | 'RECEIVED' | 'SOLD' | 'RECALLED';
    verified: boolean;
}
