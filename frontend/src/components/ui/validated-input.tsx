'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Input } from './input';
import { Button } from './button'; // Added import
import { cn, validateApiKey, validateAdminKey, validateUrl, type ValidationResult } from '@/lib/utils';
import { CheckCircle, AlertCircle, Eye, EyeOff } from 'lucide-react';

export type ValidationType = 'api-key' | 'admin-key' | 'url' | 'custom';

interface ValidatedInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange'> {
  value: string;
  onChange: (value: string) => void;
  validationType?: ValidationType;
  customValidator?: (value: string) => ValidationResult;
  showValidation?: boolean;
  validateOnBlur?: boolean;
  validateOnChange?: boolean;
  onValidationChange?: (result: ValidationResult) => void;
  label?: string;
  helpText?: string;
  showPasswordToggle?: boolean;
}

export function ValidatedInput({
  value,
  onChange,
  validationType = 'custom',
  customValidator,
  showValidation = true,
  validateOnBlur = true,
  validateOnChange = false,
  onValidationChange,
  label,
  helpText,
  showPasswordToggle = false,
  className,
  type,
  ...props
}: ValidatedInputProps) {
  const [validation, setValidation] = useState<ValidationResult>({ isValid: true });
  const [touched, setTouched] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const validate = useCallback(
    (val: string): ValidationResult => {
      if (!val || val.trim() === '') {
        return { isValid: true }; // Don't show error for empty untouched fields
      }

      switch (validationType) {
        case 'api-key':
          return validateApiKey(val);
        case 'admin-key':
          return validateAdminKey(val);
        case 'url':
          return validateUrl(val);
        case 'custom':
          return customValidator ? customValidator(val) : { isValid: true };
        default:
          return { isValid: true };
      }
    },
    [validationType, customValidator]
  );

  useEffect(() => {
    if (validateOnChange && touched) {
      const result = validate(value);
      setValidation(result);
      onValidationChange?.(result);
    }
  }, [value, validateOnChange, touched, validate, onValidationChange]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value);
  };

  const handleBlur = () => {
    setTouched(true);
    if (validateOnBlur) {
      const result = validate(value);
      setValidation(result);
      onValidationChange?.(result);
    }
  };

  const inputType = showPasswordToggle
    ? (showPassword ? 'text' : 'password')
    : type;

  const showError = showValidation && touched && !validation.isValid && value.length > 0;
  const showSuccess = showValidation && touched && validation.isValid && value.length > 0;

  return (
    <div className="space-y-1.5">
      {label && (
        <label className="text-sm font-medium">
          {label}
          {props.required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}

      <div className="relative">
        <Input
          {...props}
          type={inputType}
          value={value}
          onChange={handleChange}
          onBlur={handleBlur}
          className={cn(
            className,
            showError && 'border-red-500 focus-visible:ring-red-500',
            showSuccess && 'border-green-500 focus-visible:ring-green-500',
            (showPasswordToggle || showValidation) && 'pr-10'
          )}
          aria-invalid={showError}
          aria-describedby={showError ? `${props.id}-error` : undefined}
        />

        <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1">
          {showValidation && touched && value.length > 0 && (
            <>
              {showError && (
                <AlertCircle className="h-4 w-4 text-red-500" aria-hidden="true" />
              )}
              {showSuccess && (
                <CheckCircle className="h-4 w-4 text-green-500" aria-hidden="true" />
              )}
            </>
          )}

          {showPasswordToggle && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => setShowPassword(!showPassword)}
              className="h-6 w-6 hover:bg-muted"
              tabIndex={-1}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? (
                <EyeOff className="h-4 w-4 text-muted-foreground" />
              ) : (
                <Eye className="h-4 w-4 text-muted-foreground" />
              )}
            </Button>
          )}
        </div>
      </div>

      {helpText && !showError && (
        <p className="text-xs text-muted-foreground">{helpText}</p>
      )}

      {showError && (
        <p
          id={`${props.id}-error`}
          className="text-xs text-red-500 flex items-center gap-1"
          role="alert"
        >
          {validation.error}
        </p>
      )}
    </div>
  );
}

// Specialized pre-configured inputs

interface ApiKeyInputProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  disabled?: boolean;
  autoFilled?: boolean;
}

export function ApiKeyInput({ value, onChange, label = 'API Key', disabled, autoFilled }: ApiKeyInputProps) {
  return (
    <div className="space-y-1.5">
      <ValidatedInput
        id="api-key"
        value={value}
        onChange={onChange}
        validationType="api-key"
        label={label}
        placeholder="rge_..."
        helpText={autoFilled ? 'Using your saved API key' : 'Your RegEngine API key starting with "rge_"'}
        showPasswordToggle
        disabled={disabled}
        data-tutorial="api-key-input"
      />
    </div>
  );
}

export function AdminKeyInput({ value, onChange, label = 'Admin Master Key', disabled }: ApiKeyInputProps) {
  return (
    <ValidatedInput
      id="admin-key"
      value={value}
      onChange={onChange}
      validationType="admin-key"
      label={label}
      placeholder="Enter your admin master key"
      helpText="Found in your .env file as ADMIN_MASTER_KEY"
      showPasswordToggle
      disabled={disabled}
    />
  );
}

interface UrlInputProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  disabled?: boolean;
}

export function UrlInput({ value, onChange, label = 'Document URL', disabled }: UrlInputProps) {
  return (
    <ValidatedInput
      id="url"
      value={value}
      onChange={onChange}
      validationType="url"
      label={label}
      placeholder="https://example.com/regulatory-document.pdf"
      helpText="Publicly accessible URL to a PDF, HTML, or JSON document"
      disabled={disabled}
      data-tutorial="url-input"
    />
  );
}
