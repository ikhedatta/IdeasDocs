import type { SourceType } from '@/lib/types';
import {
  Cloud,
  BookOpen,
  MessageCircle,
  HardDrive,
  Mail,
  CheckSquare,
  Inbox,
  Database,
  GitBranch,
  Github,
  Headphones,
  ListChecks,
} from 'lucide-react';

const ICON_MAP: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  cloud: Cloud,
  'book-open': BookOpen,
  'message-circle': MessageCircle,
  'hard-drive': HardDrive,
  mail: Mail,
  'check-square': CheckSquare,
  inbox: Inbox,
  database: Database,
  gitlab: GitBranch,
  github: Github,
  'git-branch': GitBranch,
  headphones: Headphones,
  'list-checks': ListChecks,
};

const COLOR_MAP: Record<string, string> = {
  s3: 'text-orange-500 bg-orange-50',
  confluence: 'text-blue-600 bg-blue-50',
  discord: 'text-indigo-500 bg-indigo-50',
  google_drive: 'text-green-500 bg-green-50',
  gmail: 'text-red-500 bg-red-50',
  jira: 'text-blue-500 bg-blue-50',
  dropbox: 'text-blue-400 bg-blue-50',
  gcs: 'text-blue-600 bg-blue-50',
  gitlab: 'text-orange-600 bg-orange-50',
  github: 'text-gray-800 bg-gray-100',
  bitbucket: 'text-blue-700 bg-blue-50',
  zendesk: 'text-green-600 bg-green-50',
  asana: 'text-pink-500 bg-pink-50',
};

interface SourceIconProps {
  sourceType: SourceType | string;
  size?: number;
  className?: string;
}

export function SourceIcon({ sourceType, size = 24, className = '' }: SourceIconProps) {
  // Map source_type to icon name via a lookup
  const iconName = SOURCE_ICON_MAP[sourceType] || 'database';
  const Icon = ICON_MAP[iconName] || Database;
  const colors = COLOR_MAP[sourceType] || 'text-gray-500 bg-gray-50';

  return (
    <div
      className={`inline-flex items-center justify-center rounded-lg ${colors} ${className}`}
      style={{ width: size + 12, height: size + 12 }}
    >
      <Icon size={size * 0.6} />
    </div>
  );
}

const SOURCE_ICON_MAP: Record<string, string> = {
  s3: 'cloud',
  confluence: 'book-open',
  discord: 'message-circle',
  google_drive: 'hard-drive',
  gmail: 'mail',
  jira: 'check-square',
  dropbox: 'inbox',
  gcs: 'database',
  gitlab: 'gitlab',
  github: 'github',
  bitbucket: 'git-branch',
  zendesk: 'headphones',
  asana: 'list-checks',
};
