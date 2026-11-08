import type * as React from 'react';

export type IconName = 'search' | 'play' | 'key' | 'sound-off' | 'arrow-right' | 'chevron-right';
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

export interface SectionHeaderProps { title: string; tag?: string; meta?: string; action?: React.ReactNode; level?: 2 | 3; id?: string }
export declare function SectionHeader(props: SectionHeaderProps): React.ReactElement;

export interface BentoGridProps { row?: 'hero' | 'rank' | 'topic'; children: React.ReactNode }
export declare function BentoGrid(props: BentoGridProps): React.ReactElement;

export interface VideoTileProps { image: string; alt?: string; title: string; subtitle?: string; eyebrow?: string; badge?: React.ReactNode;
  action?: React.ReactNode; size?: 'hero' | 'md' | 'sm'; cols?: 1 | 2 | 3 | 4; rows?: 1 | 2; focus?: 'top' | string; href?: string }
export declare function VideoTile(props: VideoTileProps): React.ReactElement;

export interface ThemeTileProps { eyebrow: string; title: string; note?: string; cols?: 1 | 2; rows?: 1 | 2; href?: string }
export declare function ThemeTile(props: ThemeTileProps): React.ReactElement;

export interface RankTileProps { rank: number | string; image: string; title: string; subtitle?: string; move?: Move; cols?: 1 | 2; rows?: 1 | 2; focus?: 'top' | string; href?: string }
export declare function RankTile(props: RankTileProps): React.ReactElement;

export interface RankRowProps { rank: number | string; image: string; title: string; move?: Move; focus?: 'top'; href?: string }
export declare function RankRow(props: RankRowProps): React.ReactElement;

export interface DaySlotProps { day: string; title: string; time: string; today?: boolean; href?: string }
export declare function DaySlot(props: DaySlotProps): React.ReactElement;

export interface ActorCardProps { image: string; name: string; handle: string; role?: string; works?: string; href?: string }
export declare function ActorCard(props: ActorCardProps): React.ReactElement;

declare global { interface Window { Midea: { Logo: typeof Logo; Icon: typeof Icon; Button: typeof Button; SignInButton: typeof SignInButton;
  SearchField: typeof SearchField; SegmentedTabs: typeof SegmentedTabs; SiteHeader: typeof SiteHeader; SiteFooter: typeof SiteFooter;
  Badge: typeof Badge; Tag: typeof Tag; ProgressBar: typeof ProgressBar; SectionHeader: typeof SectionHeader; BentoGrid: typeof BentoGrid;
  VideoTile: typeof VideoTile; ThemeTile: typeof ThemeTile; RankTile: typeof RankTile; RankRow: typeof RankRow; DaySlot: typeof DaySlot;
  ActorCard: typeof ActorCard } } }
