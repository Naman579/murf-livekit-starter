import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Neo',
    short_name: 'Neo',
    description: 'Build and deploy the best web experiences with the AI Cloud',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    background_color: '#000000',
    theme_color: '#000000',
    lang: 'en',
    icons: [
      {
        src: '/icons/neo-192.png',
        sizes: '192x192',
        type: 'image/png',
      },
      {
        src: '/icons/neo-512.png',
        sizes: '512x512',
        type: 'image/png',
      },
    ],
  };
}
