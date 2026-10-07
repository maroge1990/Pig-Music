(() => {
        let appearance = 'system';
        try { appearance = localStorage.getItem('pig-music-appearance') || 'system'; } catch {}
        const theme = appearance === 'light' || appearance === 'dark' ? appearance : matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        document.documentElement.dataset.theme = theme;
        document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#15111A' : '#FBF8FA';
      })();
