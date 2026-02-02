'use client';

import { useCallback, useEffect, useState, useRef } from 'react';

interface ResizeHandleProps {
  onResize: (delta: number) => void;
  onResizeStart?: () => void;
  onResizeEnd?: () => void;
  direction?: 'horizontal' | 'vertical';
  className?: string;
}

export default function ResizeHandle({
  onResize,
  onResizeStart,
  onResizeEnd,
  direction = 'horizontal',
  className = ''
}: ResizeHandleProps) {
  const [isDragging, setIsDragging] = useState(false);
  const lastPosRef = useRef(0);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    lastPosRef.current = direction === 'horizontal' ? e.clientX : e.clientY;
    onResizeStart?.();
  }, [direction, onResizeStart]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const currentPos = direction === 'horizontal' ? e.clientX : e.clientY;
      const delta = currentPos - lastPosRef.current;

      // Only trigger resize if there's actual movement
      if (delta !== 0) {
        onResize(delta);
        lastPosRef.current = currentPos;
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      onResizeEnd?.();
    };

    // Use requestAnimationFrame for smoother updates
    let frameId: number | null = null;
    const throttledMouseMove = (e: MouseEvent) => {
      if (frameId) return;
      frameId = requestAnimationFrame(() => {
        handleMouseMove(e);
        frameId = null;
      });
    };

    document.addEventListener('mousemove', throttledMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', throttledMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      if (frameId) cancelAnimationFrame(frameId);
    };
  }, [isDragging, direction, onResize, onResizeEnd]);

  const isHorizontal = direction === 'horizontal';

  return (
    <div
      onMouseDown={handleMouseDown}
      className={`
        ${isHorizontal ? 'w-[3px] cursor-col-resize' : 'h-[3px] cursor-row-resize'}
        bg-transparent hover:bg-green2/30 transition-colors duration-200
        flex-shrink-0 relative group
        ${isDragging ? 'bg-green2/50' : ''}
        ${className}
      `}
    >
      {/* Larger hit area for easier grabbing */}
      <div
        className={`
          absolute
          ${isHorizontal ? 'inset-y-0 -left-1.5 -right-1.5' : 'inset-x-0 -top-1.5 -bottom-1.5'}
        `}
      />
      {/* Subtle visual indicator on hover */}
      <div
        className={`
          absolute opacity-0 group-hover:opacity-100 transition-opacity duration-200
          ${isHorizontal
            ? 'top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-0.5 h-6 rounded-full bg-green2/60'
            : 'top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-0.5 w-6 rounded-full bg-green2/60'
          }
        `}
      />
    </div>
  );
}
