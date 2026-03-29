'use client';

import { T } from './constants';

export default function PageStyles() {
    return (
        <style>{`
            @keyframes pulse-dot {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            @keyframes pulse-ring {
                0% { box-shadow: 0 0 0 0 ${T.accent}60; }
                70% { box-shadow: 0 0 0 10px ${T.accent}00; }
                100% { box-shadow: 0 0 0 0 ${T.accent}00; }
            }
            @keyframes exit-popup-in {
                from { opacity: 0; transform: scale(0.9) translateY(20px); }
                to { opacity: 1; transform: scale(1) translateY(0); }
            }
            input[type="range"] {
                -webkit-appearance: none;
                width: 100%;
                height: 8px;
                border-radius: 4px;
                background: var(--re-surface-border);
                outline: none;
                touch-action: manipulation;
            }
            input[type="range"]::-webkit-slider-thumb {
                -webkit-appearance: none;
                width: 28px;
                height: 28px;
                border-radius: 50%;
                background: ${T.accent};
                cursor: pointer;
                border: 3px solid ${T.bg};
                box-shadow: 0 0 10px ${T.accent}40;
                touch-action: manipulation;
            }
            input[type="range"]::-moz-range-thumb {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                background: ${T.accent};
                cursor: pointer;
                border: 3px solid ${T.bg};
            }
            input[type="range"] {
                touch-action: manipulation;
            }
            input::placeholder { color: ${T.textDim}; }
            * { box-sizing: border-box; margin: 0; }

            /* CTA hover lift */
            .re-cta-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 24px ${T.accent}50 !important; }
            .re-cta-secondary:hover { border-color: ${T.borderHover} !important; background: ${T.surface} !important; }

            /* Mobile responsive */
            @media (max-width: 768px) {
                .competitor-row {
                    grid-template-columns: 1.2fr 1fr 1fr 1fr !important;
                    padding: 10px 12px !important;
                    font-size: 11px !important;
                }
                .competitor-row span {
                    font-size: 11px !important;
                }
            }
            @media (max-width: 480px) {
                .competitor-row {
                    grid-template-columns: 1fr 1fr !important;
                }
                .competitor-row span:nth-child(3),
                .competitor-row span:nth-child(4) {
                    display: none !important;
                }
            }
        `}</style>
    );
}
