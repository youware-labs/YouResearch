'use client';

import { Loader2, CheckCircle2, Circle, ListChecks } from 'lucide-react';

export interface Task {
  id: string;
  title: string;
  status: 'pending' | 'in_progress' | 'completed';
}

export interface TaskListProps {
  mainTask: string;
  tasks: Task[];
  isCollapsible?: boolean;
}

/**
 * TaskList - Inline task progress display
 *
 * Shows a main task with subtasks that can be checked off.
 * Similar to Claude Code's todo list UI.
 */
export default function TaskList({ mainTask, tasks, isCollapsible: _isCollapsible = false }: TaskListProps) {
  const completedCount = tasks.filter(t => t.status === 'completed').length;
  const inProgressTask = tasks.find(t => t.status === 'in_progress');

  return (
    <div className="bg-fill-secondary rounded-yw-lg border border-black/6 overflow-hidden my-2">
      {/* Main Task Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-orange2/30 border-b border-orange1/20">
        <ListChecks size={14} className="text-orange1 flex-shrink-0" />
        <span className="typo-small-strong text-orange1 truncate">{mainTask}</span>
        {tasks.length > 0 && (
          <span className="typo-ex-small text-orange1/70 ml-auto flex-shrink-0">
            ({completedCount}/{tasks.length})
          </span>
        )}
      </div>

      {/* Subtasks */}
      {tasks.length > 0 && (
        <div className="px-3 py-2 space-y-1.5">
          {tasks.map((task) => (
            <div key={task.id} className="flex items-start gap-2">
              {/* Status Icon */}
              <div className="flex-shrink-0 mt-0.5">
                {task.status === 'completed' ? (
                  <CheckCircle2 size={14} className="text-success" />
                ) : task.status === 'in_progress' ? (
                  <Loader2 size={14} className="text-orange1 animate-spin" />
                ) : (
                  <Circle size={14} className="text-tertiary" />
                )}
              </div>

              {/* Task Title */}
              <span
                className={`typo-small leading-tight ${
                  task.status === 'completed'
                    ? 'text-tertiary line-through'
                    : task.status === 'in_progress'
                    ? 'text-primary font-medium'
                    : 'text-secondary'
                }`}
              >
                {task.title}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* In-progress indicator at bottom */}
      {inProgressTask && (
        <div className="px-3 py-1.5 bg-orange2/20 border-t border-orange1/10">
          <span className="typo-ex-small text-orange1">
            Working on: {inProgressTask.title}
          </span>
        </div>
      )}
    </div>
  );
}
