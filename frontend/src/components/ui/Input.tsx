import { forwardRef, InputHTMLAttributes } from 'react';
import { clsx } from 'clsx';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string | { message?: string } | undefined;
}

function getErrorMessage(error: string | { message?: string } | { type: string; message: string } | { loc: string[]; msg: string; type: string; input: any; url?: string } | { message: string } | undefined): string | undefined {
  if (!error) return undefined;
  if (typeof error === 'string') return error;
  if ('message' in error && typeof error.message === 'string') return error.message;
  if ('msg' in error && typeof error.msg === 'string') return error.msg;
  if ('type' in error) return 'Invalid value';
  return 'Invalid value';
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
    const errorMessage = getErrorMessage(error);
    
    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={clsx(
            'flex h-11 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:outline-none transition-shadow focus:ring-2 focus:ring-primary-500/30 focus:border-transparent dark:border-gray-600 dark:bg-gray-800 dark:text-white',
            errorMessage && 'border-red-500 focus:ring-red-500',
            className
          )}
          aria-invalid={errorMessage ? 'true' : 'false'}
          aria-describedby={errorMessage ? `${inputId}-error` : undefined}
          {...props}
        />
        {errorMessage && (
          <p id={`${inputId}-error`} className="mt-1 text-sm text-red-600 dark:text-red-400" role="alert">
            {errorMessage}
          </p>
        )}
      </div>
    )
  }
);

Input.displayName = 'Input';