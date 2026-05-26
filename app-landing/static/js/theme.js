document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('theme-toggle');
    const body = document.body;

    // Load saved theme preference
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        body.classList.add('dark-theme');
        updateThemeIcon('dark');
    } else {
        body.classList.remove('dark-theme');
        updateThemeIcon('light');
    }

    // Toggle theme on button click
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const isDark = body.classList.toggle('dark-theme');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            updateThemeIcon(isDark ? 'dark' : 'light');
        });
    }

    // Update SVG icon based on theme
    function updateThemeIcon(theme) {
        if (!themeToggle) return;
        const svg = themeToggle.querySelector('svg');
        if (!svg) return;

        if (theme === 'dark') {
            // Moon icon for dark mode
            svg.innerHTML = `
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" fill="currentColor" stroke="none"/>
            `;
        } else {
            // Sun icon for light mode
            svg.innerHTML = `
                <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.8"></circle>
                <path d="M12 3V5.5M12 18.5V21M3 12H5.5M18.5 12H21M5.7 5.7L7.4 7.4M16.6 16.6L18.3 18.3M16.6 7.4L18.3 5.7M5.7 18.3L7.4 16.6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"></path>
            `;
        }
    }
});
