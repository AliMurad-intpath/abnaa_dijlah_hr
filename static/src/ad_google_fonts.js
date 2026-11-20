/** @odoo-module **/
// Makes the web client read Times New Roman (via its metric-compatible Google Fonts twin, Tinos)
// and Amiri for Arabic. Falls back silently to the font files bundled in static/fonts when offline.
const ID = "ad-google-fonts";
if (typeof document !== "undefined" && !document.getElementById(ID)) {
    const link = document.createElement("link");
    link.id = ID;
    link.rel = "stylesheet";
    link.href = "https://fonts.googleapis.com/css2?family=Tinos:ital,wght@0,400;0,700;1,400;1,700&family=Amiri:wght@400;700&display=swap";
    document.head.appendChild(link);
}
