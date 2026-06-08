import { useEffect } from 'react';

export function useNavScrollEffect() {
  useEffect(() => {
    const nav = document.querySelector('.site-header-nav');
    if (!nav) return;

    const onScroll = () => {
      nav.classList.toggle('site-header-nav--scrolled', window.scrollY > 8);
    };

    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
}
