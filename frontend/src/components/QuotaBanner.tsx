// components/coach/QuotaBanner.tsx
'use client';

import { useState } from 'react';
import { X, Zap, AlertTriangle, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface QuotaBannerProps {
  level: 'notice' | 'urgent' | 'critical';
  message: string;
  subtext: string;
  usage: {
    used: number;
    limit: number;
    remaining: number;
  };
  action: {
    text: string;
    link: string;
  };
  onDismiss?: () => void;
}

const config = {
  notice: {
    icon: Zap,
    gradient: 'from-amber-500/10 to-orange-500/10',
    border: 'border-amber-200',
    iconBg: 'bg-amber-100',
    iconColor: 'text-amber-600',
    titleColor: 'text-amber-900',
    textColor: 'text-amber-700',
    button: 'bg-amber-600 hover:bg-amber-700 text-white',
  },
  urgent: {
    icon: AlertTriangle,
    gradient: 'from-orange-500/10 to-red-500/10',
    border: 'border-orange-200',
    iconBg: 'bg-orange-100',
    iconColor: 'text-orange-600',
    titleColor: 'text-orange-900',
    textColor: 'text-orange-700',
    button: 'bg-orange-600 hover:bg-orange-700 text-white',
  },
  critical: {
    icon: AlertCircle,
    gradient: 'from-red-500/10 to-rose-500/10',
    border: 'border-red-200',
    iconBg: 'bg-red-100',
    iconColor: 'text-red-600',
    titleColor: 'text-red-900',
    textColor: 'text-red-700',
    button: 'bg-red-600 hover:bg-red-700 text-white',
  },
};

export function QuotaBanner({ 
  level, 
  message, 
  subtext, 
  usage, 
  action,
  onDismiss 
}: QuotaBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  const style = config[level];
  const Icon = style.icon;

  if (dismissed) return null;

  const handleDismiss = () => {
    setDismissed(true);
    onDismiss?.();
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className={`relative mb-4 overflow-hidden rounded-xl border ${style.border} bg-gradient-to-r ${style.gradient} backdrop-blur-sm`}
      >
        <div className="relative flex items-start gap-4 p-4">
          {/* Icon */}
          <div className={`flex-shrink-0 rounded-lg ${style.iconBg} p-2`}>
            <Icon className={`h-5 w-5 ${style.iconColor}`} />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <h4 className={`font-semibold ${style.titleColor}`}>
              {message}
            </h4>
            <p className={`mt-0.5 text-sm ${style.textColor}`}>
              {subtext}
            </p>
            
            {/* Usage bar */}
            <div className="mt-3 flex items-center gap-3">
              <div className="flex-1 h-1.5 bg-white/50 rounded-full overflow-hidden">
                <div 
                  className={`h-full rounded-full transition-all duration-500 ${
                    level === 'critical' ? 'bg-red-500 w-full' :
                    level === 'urgent' ? 'bg-orange-500' :
                    'bg-amber-500'
                  }`}
                  style={{ 
                    width: level === 'urgent' ? '90%' : 
                           level === 'notice' ? `${(usage.used / usage.limit) * 100}%` : 
                           '100%' 
                  }}
                />
              </div>
              <span className={`text-xs font-medium ${style.textColor}`}>
                {usage.used}/{usage.limit}
              </span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => window.location.href = action.link}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${style.button}`}
            >
              {action.text}
            </button>
            <button
              onClick={handleDismiss}
              className={`p-1.5 rounded-lg hover:bg-white/20 transition-colors ${style.textColor}`}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}