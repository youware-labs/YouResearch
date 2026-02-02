'use client';

import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  CheckCircle,
  Circle,
  Loader2,
  XCircle,
  SkipForward,
  ListTodo,
} from 'lucide-react';

export interface PlanStep {
  step_number: number;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped';
  files?: string[];
}

export interface Plan {
  plan_id: string;
  goal: string;
  steps: PlanStep[];
  complexity: number;
}

interface PlanDisplayProps {
  plan: Plan;
  onClear?: () => void;
}

function StepStatusIcon({ status }: { status: PlanStep['status'] }) {
  switch (status) {
    case 'completed':
      return <CheckCircle size={16} className="text-success flex-shrink-0" />;
    case 'in_progress':
      return <Loader2 size={16} className="text-green2 animate-spin flex-shrink-0" />;
    case 'failed':
      return <XCircle size={16} className="text-error flex-shrink-0" />;
    case 'skipped':
      return <SkipForward size={16} className="text-tertiary flex-shrink-0" />;
    default:
      return <Circle size={16} className="text-tertiary flex-shrink-0" />;
  }
}

export default function PlanDisplay({ plan, onClear }: PlanDisplayProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const completedCount = plan.steps.filter(s => s.status === 'completed').length;
  const totalSteps = plan.steps.length;
  const progressPercent = totalSteps > 0 ? Math.round((completedCount / totalSteps) * 100) : 0;

  const isComplete = completedCount === totalSteps && totalSteps > 0;

  return (
    <div className={`rounded-yw-lg border ${isComplete ? 'bg-green3/30 border-green2/30' : 'bg-fill-secondary border-black/6'} overflow-hidden my-2`}>
      {/* Header */}
      <div
        className="flex items-center gap-2 p-2.5 cursor-pointer hover:bg-black/3 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? (
          <ChevronDown size={14} className="text-tertiary flex-shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-tertiary flex-shrink-0" />
        )}
        <ListTodo size={14} className="text-green2 flex-shrink-0" />
        <span className="typo-small-strong text-green1 flex-1 truncate">{plan.goal}</span>

        {/* Progress indicator */}
        <div className="flex items-center gap-2">
          <span className="typo-ex-small text-tertiary">
            {completedCount}/{totalSteps}
          </span>
          <div className="w-16 h-1.5 bg-black/6 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${isComplete ? 'bg-success' : 'bg-green2'}`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </div>

      {/* Steps list */}
      {isExpanded && (
        <div className="border-t border-black/6">
          {plan.steps.map((step) => (
            <div
              key={step.step_number}
              className={`flex items-start gap-2.5 px-3 py-2 border-b border-black/6 last:border-b-0 ${
                step.status === 'in_progress' ? 'bg-green3/20' : ''
              }`}
            >
              <StepStatusIcon status={step.status} />
              <div className="flex-1 min-w-0">
                <div className={`typo-small ${step.status === 'completed' ? 'text-secondary line-through' : 'text-primary'}`}>
                  <span className="text-tertiary mr-1">{step.step_number}.</span>
                  {step.title}
                </div>
                {step.description && step.status === 'in_progress' && (
                  <div className="typo-ex-small text-tertiary mt-0.5 line-clamp-2">
                    {step.description}
                  </div>
                )}
                {step.files && step.files.length > 0 && step.status === 'in_progress' && (
                  <div className="typo-ex-small text-green2 mt-0.5">
                    Files: {step.files.join(', ')}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Footer with clear button when complete */}
          {isComplete && onClear && (
            <div className="p-2 border-t border-black/6 bg-green3/10">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onClear();
                }}
                className="typo-ex-small text-tertiary hover:text-primary transition-colors"
              >
                Clear plan
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
