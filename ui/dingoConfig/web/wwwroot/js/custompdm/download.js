// custom-pdm (route B phase B5): save a text file from the browser (the /pdm Export DBC button)
export function downloadText(fileName, text) {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// custom-pdm (uiwalk): bring an element into view, e.g. the trigger editor that opens under the 24-row list
export function scrollIntoView(id) {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
}
