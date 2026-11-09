import type * as React from 'react';

export type IconName = 'search' | 'play' | 'key' | 'sound-off' | 'arrow-right' | 'chevron-right'
  | 'heart' | 'sparkle' | 'smile' | 'tear' | 'plus' | 'x' | 'bookmark' | 'share' | 'eye' | 'people' | 'sound' | 'expand'
  | 'home' | 'calendar' | 'grid' | 'user' | 'check' | 'flag' | 'send' | 'chat' | 'star' | 'back' | 'pause' | 'list' | 'cc' | 'rotate'
  | 'pen' | 'film' | 'news' | 'repo' | 'paper' | 'quote' | 'link';
export type Move = 'new' | 'up' | 'down' | 'same';

export interface LogoProps { size?: number; mark?: boolean; href?: string }
export declare function Logo(props: LogoProps): React.ReactElement;

export interface IconProps { name: IconName; size?: number }
export declare function Icon(props: IconProps): React.ReactElement;

export interface ButtonProps { variant?: 'primary' | 'secondary' | 'ghost' | 'light'; size?: 'md' | 'lg'; icon?: IconName; href?: string;
  onClick?: () => void; disabled?: boolean; type?: 'button' | 'submit'; children?: React.ReactNode }
export declare function Button(props: ButtonProps): React.ReactElement;

export interface SignInButtonProps { variant?: 'primary' | 'outline'; href?: string; onClick?: () => void; children?: React.ReactNode }
export declare function SignInButton(props: SignInButtonProps): React.ReactElement;

export interface SearchFieldProps { placeholder?: string; label?: string; value?: string; onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void }
export declare function SearchField(props: SearchFieldProps): React.ReactElement;

export interface SegmentedTabsProps { options: { value: string; label: string }[]; value?: string; defaultValue?: string; onChange?: (value: string) => void; label?: string }
export declare function SegmentedTabs(props: SegmentedTabsProps): React.ReactElement;

export interface SiteHeaderProps { items: { label: string; href?: string; active?: boolean }[]; search?: boolean; searchPlaceholder?: string; account?: React.ReactNode }
export declare function SiteHeader(props: SiteHeaderProps): React.ReactElement;

export interface SiteFooterProps { note?: string; links?: { label: string; href: string }[] }
export declare function SiteFooter(props: SiteFooterProps): React.ReactElement;

export interface BadgeProps { tone?: 'live' | 'now' | Move | 'neutral'; dot?: boolean; children?: React.ReactNode }
export declare function Badge(props: BadgeProps): React.ReactElement;

export interface TagProps { children: React.ReactNode }
export declare function Tag(props: TagProps): React.ReactElement;

export interface ProgressBarProps { value: number; label?: string }
export declare function ProgressBar(props: ProgressBarProps): React.ReactElement;

export interface SectionHeaderProps { title: string; tag?: string; meta?: string; action?: React.ReactNode; level?: 1 | 2 | 3; id?: string }
export declare function SectionHeader(props: SectionHeaderProps): React.ReactElement;

export interface BentoGridProps { row?: 'hero' | 'rank' | 'topic'; children: React.ReactNode }
export declare function BentoGrid(props: BentoGridProps): React.ReactElement;

export interface VideoTileProps { image: string; alt?: string; title: string; subtitle?: string; eyebrow?: string; badge?: React.ReactNode;
  action?: React.ReactNode; corner?: React.ReactNode; size?: 'hero' | 'md' | 'sm'; cols?: 1 | 2 | 3 | 4; rows?: 1 | 2; focus?: 'top' | string; href?: string }
export declare function VideoTile(props: VideoTileProps): React.ReactElement;

export interface ThemeTileProps { eyebrow: string; title: string; note?: string; cols?: 1 | 2; rows?: 1 | 2; href?: string }
export declare function ThemeTile(props: ThemeTileProps): React.ReactElement;

export interface RankTileProps { rank: number | string; image: string; title: string; subtitle?: string; move?: Move; cols?: 1 | 2; rows?: 1 | 2; focus?: 'top' | string; href?: string }
export declare function RankTile(props: RankTileProps): React.ReactElement;

export interface RankRowProps { rank: number | string; image: string; title: string; move?: Move; focus?: 'top'; href?: string }
export declare function RankRow(props: RankRowProps): React.ReactElement;

export interface DaySlotProps { day: string; title: string; time: string; today?: boolean; href?: string; tag?: React.ReactNode }
export declare function DaySlot(props: DaySlotProps): React.ReactElement;

export interface ActorCardProps { image: string; name: string; handle: string; role?: string; works?: string; href?: string }
export declare function ActorCard(props: ActorCardProps): React.ReactElement;

/* ---- v2: playback, sign-in, feedback & interaction ---- */
export interface InfluenceTagProps { children: React.ReactNode }
export declare function InfluenceTag(props: InfluenceTagProps): React.ReactElement;

export interface ViewerCountProps { count: number | null; label?: string | ((n: number) => string); min?: number; onImage?: boolean }
export declare function ViewerCount(props: ViewerCountProps): React.ReactElement | null;

export interface ReactionOption { value: string; label: string; icon?: IconName; askReason?: boolean }
export interface ReactionBarProps { options: ReactionOption[]; value?: string | null; onChange?: (value: string | null, reason: string | null) => void;
  title?: string; label?: string; note?: string; reasons?: { value: string; label: string }[]; reasonPrompt?: string; skipLabel?: string; compact?: boolean }
export declare function ReactionBar(props: ReactionBarProps): React.ReactElement;

export interface LiveReactionsProps { options: { value: string; label: string; icon: IconName }[]; onReact?: (value: string) => void;
  burst?: Record<string, number>; hidden?: boolean; onToggleHidden?: () => void; toggleLabel?: string; label?: string; cooldownMs?: number }
export declare function LiveReactions(props: LiveReactionsProps): React.ReactElement;

export interface PollOption { id: string; title: string; sub?: string; images?: string[]; share?: number | null }
export interface PollCardProps { variant?: 'tile' | 'full' | 'overlay'; eyebrow?: string; title: string; options: PollOption[]; value?: string | null;
  onVote?: (id: string) => void; cta?: string; note?: string; closed?: boolean; winner?: string | null; allowChange?: boolean;
  optionsLabel?: string; cols?: 1 | 2; rows?: 1 | 2 }
export declare function PollCard(props: PollCardProps): React.ReactElement;

export interface LivePlayerProps { src: string; poster?: string; offset?: number; muted?: boolean; onEnded?: () => void; onTime?: (t: number) => void;
  badge?: React.ReactNode; topRight?: React.ReactNode; label?: string; unmuteLabel?: string; muteLabel?: string; fullscreenLabel?: string;
  className?: string; children?: React.ReactNode }
export declare function LivePlayer(props: LivePlayerProps): React.ReactElement;

export interface VideoPlayerProps { src: string; poster?: string; captions?: string | null; captionsLabel?: string; captionsLang?: string;
  vertical?: boolean; autoPlay?: boolean; duration?: number; label?: string;
  highlights?: { start: number; end: number; label: string }[]; highlightsLabel?: string;
  onProgress?: (seconds: number, duration: number, ended: boolean) => void; onEnded?: () => void }
export declare function VideoPlayer(props: VideoPlayerProps): React.ReactElement;

export interface VideoMetaProps { title: string; eyebrow?: string; meta?: string; tags?: React.ReactNode[] | null; actions?: React.ReactNode; as?: 'h1' | 'h2' }
export declare function VideoMeta(props: VideoMetaProps): React.ReactElement;

export interface AIDisclosureProps { children: React.ReactNode }
export declare function AIDisclosure(props: AIDisclosureProps): React.ReactElement;

export interface SignInDialogProps { open: boolean; onClose: () => void; title: string; body?: string; closeLabel?: string;
  popupLabel?: string; onPopup: () => void; redirectLabel?: string; onRedirect?: () => void; qr?: React.ReactNode; qrLabel?: string;
  error?: string; footer?: string }
export declare function SignInDialog(props: SignInDialogProps): React.ReactElement;

export interface AccountMenuProps { name: string; sub?: string; items: { label: string; href?: string; onClick?: () => void }[] }
export declare function AccountMenu(props: AccountMenuProps): React.ReactElement;

export interface SkeletonProps { cols?: 1 | 2 | 3 | 4; rows?: 1 | 2; height?: number | string }
export declare function Skeleton(props: SkeletonProps): React.ReactElement;

export interface EmptyStateProps { title: string; body?: string; action?: React.ReactNode; cols?: 1 | 2 | 3 | 4; rows?: 1 | 2 }
export declare function EmptyState(props: EmptyStateProps): React.ReactElement;

export interface TopicBentoProps { title: string; id?: string; tag?: string; tagNode?: React.ReactNode; meta?: string; action?: React.ReactNode; level?: 2 | 3;
  videos: { image: string; title: string; subtitle?: string; href?: string; alt?: string; focus?: 'top' | string | null }[] }
export declare function TopicBento(props: TopicBentoProps): React.ReactElement;

export interface BottomNavProps { items: { label: string; href: string; icon: IconName; active?: boolean }[]; label?: string }
export declare function BottomNav(props: BottomNavProps): React.ReactElement;

/* ---- v3: community (phase 2) and schedule / topic pages ---- */
export interface ChatMessage { id: number; nickname: string; text: string; at?: number }
export interface ChatPanelProps { title: string; messages: ChatMessage[]; onSend?: (text: string) => Promise<boolean> | boolean | void;
  meta?: string | null; pinned?: string | null; pinnedLabel?: string; onReport?: (m: ChatMessage) => void; reportLabel?: string;
  signedIn?: boolean; onSignIn?: () => void; signInLabel?: string; placeholder?: string; inputLabel?: string; sendLabel?: string;
  max?: number; disabled?: boolean; notice?: string; hint?: string; composer?: boolean; collapseLabel?: string; expandLabel?: string; defaultOpen?: boolean }
export declare function ChatPanel(props: ChatPanelProps): React.ReactElement;

export interface WishCardProps { kindLabel: string; text: string; status: 'open' | 'topic' | 'producing' | 'done'; statusLabel?: string;
  progress: number; progressLabel?: string; countLabel: string; note?: string | null; supported?: boolean; supportLabel: string;
  supportedLabel: string; onSupport?: () => void; onReport?: () => void; reportLabel?: string }
export declare function WishCard(props: WishCardProps): React.ReactElement;

export interface WishComposerProps { title: string; actors: { handle: string; name: string; image: string }[]; onSubmit?: (w: { kind: 'topic' | 'cast'; text: string; actors: string[] }) => Promise<boolean> | boolean | void;
  left?: number | null; leftLabel?: string; kindLabel?: string; topicLabel: string; castLabel: string; castPick?: string;
  topicTextLabel: string; topicPlaceholder?: string; castTextLabel: string; castPlaceholder?: string; rules?: string; footer?: string;
  submitLabel: string; disabled?: boolean; max?: number }
export declare function WishComposer(props: WishComposerProps): React.ReactElement;

export interface AskActorProps { title: string; onAsk?: (text: string) => Promise<boolean> | boolean | void; inputLabel: string; placeholder?: string;
  leftLabel?: string; footer?: string; signedIn?: boolean; onSignIn?: () => void; submitLabel: string; disabled?: boolean; max?: number;
  replies?: { id: number; question: string; reply: string | null }[]; avatar?: string; actorName: string; aiLabel: string;
  youAskedLabel?: string; pendingLabel?: string; replyNote?: string }
export declare function AskActor(props: AskActorProps): React.ReactElement;

export interface AnswerTileProps { image: string; question: string; meta?: string; href?: string; aiLabel: string; cols?: 1 | 2; rows?: 1 | 2 }
export declare function AnswerTile(props: AnswerTileProps): React.ReactElement;

export interface TopicHeaderProps { title: string; eyebrow?: string; meta?: string; tags?: React.ReactNode[] }
export declare function TopicHeader(props: TopicHeaderProps): React.ReactElement;

export interface ScheduleSlot { id: string; range: string; title: string; meta: string; now?: boolean; href?: string; tag?: React.ReactNode }
export interface ScheduleDayProps { label: string; slots: ScheduleSlot[]; today?: boolean; nowLabel?: string }
export declare function ScheduleDay(props: ScheduleDayProps): React.ReactElement;
export interface ScheduleWeekProps { days: { label: string; today?: boolean; slots: ScheduleSlot[] }[]; nowLabel?: string }
export declare function ScheduleWeek(props: ScheduleWeekProps): React.ReactElement;

export type ArticleKind = 'news' | 'repo' | 'paper';
export type ArticleReaction = 'helpful' | 'sequel' | 'video' | 'question';
export interface KindChipProps { kind: ArticleKind; label?: string; children?: React.ReactNode }
export declare function KindChip(props: KindChipProps): React.ReactElement;
export interface ArticleFigureProps { wide?: string; narrow?: string; caption?: React.ReactNode | ((selected: number | null) => React.ReactNode);
  selected?: number; onSelect?: (index: number) => void; compact?: boolean }
export declare function ArticleFigure(props: ArticleFigureProps): React.ReactElement | null;
export interface ArticleTileProps { href: string; kind: ArticleKind; kindLabel: string; source?: string; figure?: string; title: string; dek?: string;
  meta?: React.ReactNode; badge?: React.ReactNode; cols?: number; rows?: number }
export declare function ArticleTile(props: ArticleTileProps): React.ReactElement;
export interface ArticleReactionsProps { options: { value: ArticleReaction; label: string; icon?: IconName }[]; value?: ArticleReaction[];
  counts?: Partial<Record<ArticleReaction, number>>; onToggle?: (kind: ArticleReaction, on: boolean) => void; bar?: boolean; label?: string }
export declare function ArticleReactions(props: ArticleReactionsProps): React.ReactElement;
export interface FollowupMeterProps { label: string; value?: number; max?: number; valueLabel?: string; note?: React.ReactNode }
export declare function FollowupMeter(props: FollowupMeterProps): React.ReactElement;
export interface QuizCardProps { question: string; options: string[]; mine?: number | null; answer?: number | null; right?: number | null;
  eyebrow?: string; onAnswer?: (index: number) => void }
export declare function QuizCard(props: QuizCardProps): React.ReactElement;
export interface SourceListProps { sources: { title?: string; url: string; source?: string }[]; label?: string }
export declare function SourceList(props: SourceListProps): React.ReactElement;

declare global { interface Window { Midea: { Logo: typeof Logo; Icon: typeof Icon; Button: typeof Button; SignInButton: typeof SignInButton;
  SearchField: typeof SearchField; SegmentedTabs: typeof SegmentedTabs; SiteHeader: typeof SiteHeader; SiteFooter: typeof SiteFooter;
  Badge: typeof Badge; Tag: typeof Tag; ProgressBar: typeof ProgressBar; SectionHeader: typeof SectionHeader; BentoGrid: typeof BentoGrid;
  VideoTile: typeof VideoTile; ThemeTile: typeof ThemeTile; RankTile: typeof RankTile; RankRow: typeof RankRow; DaySlot: typeof DaySlot;
  ActorCard: typeof ActorCard; InfluenceTag: typeof InfluenceTag; ViewerCount: typeof ViewerCount; ReactionBar: typeof ReactionBar;
  LiveReactions: typeof LiveReactions; PollCard: typeof PollCard; LivePlayer: typeof LivePlayer; VideoPlayer: typeof VideoPlayer;
  VideoMeta: typeof VideoMeta; AIDisclosure: typeof AIDisclosure; SignInDialog: typeof SignInDialog; AccountMenu: typeof AccountMenu;
  Skeleton: typeof Skeleton; EmptyState: typeof EmptyState; TopicBento: typeof TopicBento; BottomNav: typeof BottomNav;
  ChatPanel: typeof ChatPanel; WishCard: typeof WishCard; WishComposer: typeof WishComposer; AskActor: typeof AskActor; AnswerTile: typeof AnswerTile;
  TopicHeader: typeof TopicHeader; ScheduleDay: typeof ScheduleDay; ScheduleWeek: typeof ScheduleWeek;
  KindChip: typeof KindChip; ArticleFigure: typeof ArticleFigure; ArticleTile: typeof ArticleTile; ArticleReactions: typeof ArticleReactions;
  FollowupMeter: typeof FollowupMeter; QuizCard: typeof QuizCard; SourceList: typeof SourceList } } }
