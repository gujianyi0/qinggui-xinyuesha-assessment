import {
  BookOpen,
  Database,
  FolderClock,
  LibraryBig,
  MessageCircle,
} from 'lucide-react'
export type Page = 'chat' | 'library' | 'feedback' | 'jobs' | 'bookshelf'
export const NAVIGATION = [
  {
    id: 'chat' as const,
    label: '问答工作台',
    icon: MessageCircle,
    sub: '规则与结算',
  },
  {
    id: 'library' as const,
    label: '游戏资料库',
    icon: BookOpen,
    sub: '资料与已验证裁定',
  },
  {
    id: 'feedback' as const,
    label: '我的反馈',
    icon: FolderClock,
    sub: '草稿与提交记录',
  },
  {
    id: 'jobs' as const,
    label: '后台任务',
    icon: Database,
    sub: '资料导入与索引',
  },
  {
    id: 'bookshelf' as const,
    label: '知识书架',
    icon: LibraryBig,
    sub: '知识文档与考核资料',
  },
]
