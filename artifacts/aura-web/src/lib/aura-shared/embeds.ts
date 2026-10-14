export type EmbedPlatform = 'Substack' | 'X' | 'Reddit' | 'Link';
export interface EmbedPreview { url: string; hostname: string; platform: EmbedPlatform; headline: string; author: string }
export function getEmbedPreview(input: string): EmbedPreview | null {
  try {
    const url = new URL(input);
    if (!['http:', 'https:'].includes(url.protocol)) return null;
    const hostname = url.hostname.replace(/^www\./, '');
    const platform: EmbedPlatform = hostname.endsWith('substack.com') ? 'Substack' : ['x.com','twitter.com','mobile.twitter.com'].includes(hostname) ? 'X' : hostname === 'reddit.com' || hostname.endsWith('.reddit.com') ? 'Reddit' : 'Link';
    const slug = url.pathname.split('/').filter(Boolean).at(-1)?.replace(/[-_]/g, ' ').replace(/\.[^.]+$/, '');
    return { url: url.toString(), hostname, platform, headline: slug ? slug.replace(/\b\w/g, letter => letter.toUpperCase()) : `A link from ${hostname}`, author: platform === 'Substack' ? hostname.replace('.substack.com', '') : hostname };
  } catch { return null; }
}
