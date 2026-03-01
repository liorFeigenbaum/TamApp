let sourceCounter = 0;
const sourcesRegistry = {};
const DATABASE_TYPES = ["postgres", "mssql", "mysql", "oracle"];

// --------------------------------------------------
// CONNECTIONS
// --------------------------------------------------
async function add_configuration() {
    const type = document.getElementById("blockType").value;
    const container = document.getElementById("block_" + type);

    // Add header once
    if (!container.querySelector("h4")) {
        const header = document.createElement("h4");
        header.textContent = `${type.charAt(0).toUpperCase() + type.slice(1)} Configuration`;
        container.appendChild(header);
    }

    // Create / get two-columns wrapper
    let two_columns = container.querySelector(".two-columns");
    if (!two_columns) {
        two_columns = document.createElement("div");
        two_columns.className = "two-columns";
        container.appendChild(two_columns);
    }

    try {
        const response = await fetch(`/static/config_blocks/${type}.html`);
        if (!response.ok) throw new Error("Failed to fetch template");
        const html = await response.text();

        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = html;
        two_columns.appendChild(tempDiv.firstElementChild);
    } catch (err) {
        console.error("Error loading template:", err);
        alert("Failed to load configuration block HTML for " + type);
    }
}

// --------------------------------------------------
// SOURCES
// --------------------------------------------------

async function add_source(containerId) {
    const selected_connection = document.getElementById("source_connection_selector").value;
    const container = document.getElementById(containerId);

    sourceCounter++;
    const sourceId = `source_${sourceCounter}`;
    sourcesRegistry[sourceId] = sourceId;

    let type = "file";

    if (selected_connection !== "file" && selected_connection !== "") {
        const all_inputs = document.querySelectorAll("input[name$='_name[]']");
        const input = Array.from(all_inputs).find(i => i.value === selected_connection);

        if (!input) {
            alert(`Connection "${selected_connection}" not found!`);
            return;
        }

        const parentBlock = input.closest(".input-block");
        const type_input =
            parentBlock.querySelector("input[name$='_type[]'], select[name$='_type[]']");

        let raw_type = type_input ? type_input.value : "unknown";

        if (DATABASE_TYPES.includes(raw_type)) {
            type = "database";
        } else {
            type = raw_type;
        }
    }

    try {
        const response = await fetch(`/static/source_blocks/${type}.html`);
        if (!response.ok) throw new Error("Template not found");

        const html = await response.text();
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = html;

        const block = tempDiv.firstElementChild;

        const connectionInput = block.querySelector("[data-connection]");
        if (connectionInput) {
            connectionInput.value = selected_connection;
        }

        container.appendChild(block);
    } catch (err) {
        console.error(err);
        alert(`Failed to load source template for type "${type}"`);
    }
}

// --------------------------------------------------
// TRANSFORMS
// --------------------------------------------------

function add_transform() {
    const container = document.getElementById("blockTransforms");
    const block = document.createElement("div");
    block.className = "input-block";

    block.innerHTML = `
        <label>Name</label><input type="text" name="transform_name[]" placeholder="Transform Name">
        <label>Type</label><input type="text" name="transform_type[]" placeholder="Transform Type">
        <label>File Name</label><input type="text" name="transform_file[]" placeholder="File Name">
        <button type="button" class="remove-btn">Remove</button>
    `;

    container.appendChild(block);
}

// --------------------------------------------------
// SINK LISTS
// --------------------------------------------------

function generate_sink_sources_list() {
    const listContainer = document.getElementById("sink_sources_list");
    if (!listContainer) return;
    listContainer.innerHTML = "";

    document.querySelectorAll("input[name='source_name[]']").forEach((input) => {
        const div = document.createElement("div");
        div.className = "sink-source-item";
        div.innerHTML = `
            <label>
                <input type="checkbox" name="sink_sources[]" value="${input.value}">
                ${input.value}
            </label>
        `;
        listContainer.appendChild(div);
    });

    // Restore previously checked sources
    const saved = ((window._restoredSinkData || {})['sink_sources[]']) || [];
    listContainer.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        if (saved.includes(cb.value)) cb.checked = true;
    });
}

function generate_sink_transforms_list() {
    const listContainer = document.getElementById("sink_transforms_list");
    if (!listContainer) return;
    listContainer.innerHTML = "";

    document.querySelectorAll("input[name='transform_name[]']").forEach((input) => {
        const div = document.createElement("div");
        div.className = "sink-source-item";
        div.innerHTML = `
            <label>
                <input type="checkbox" name="sink_transform[]" value="${input.value}">
                ${input.value}
            </label>
        `;
        listContainer.appendChild(div);
    });

    // Restore previously checked transforms
    const saved = ((window._restoredSinkData || {})['sink_transform[]']) || [];
    listContainer.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        if (saved.includes(cb.value)) cb.checked = true;
    });
}

// --------------------------------------------------
// REMOVE BUTTON (GLOBAL)
// --------------------------------------------------

document.addEventListener("click", function (e) {
    if (e.target.classList.contains("remove-btn")) {
        e.target.closest(".input-block").remove();
    }
});

// --------------------------------------------------
// SUBMIT FALLBACK
// --------------------------------------------------

document.getElementById("wizardForm").addEventListener("submit", () => {
    const sinkNameInput = document.querySelector("input[name='sink_name']");
    if (sinkNameInput && !sinkNameInput.value) {
        sinkNameInput.value = sinkNameInput.placeholder;
    }
});

// --------------------------------------------------
// HELPERS
// --------------------------------------------------

function get_all_connection_names() {
    const names = [];
    document.querySelectorAll("input[name$='_name[]']:not([name='source_name[]'])").forEach(input => {
        if (input.value.trim()) names.push(input.value.trim());
    });
    return names;
}

function populate_source_connection_selector() {
    const select = document.getElementById("source_connection_selector");
    const selectSink = document.getElementById("sink_connection_selector");
    if (!select) return;

    select.innerHTML = "";
    selectSink.innerHTML = "";

    select.appendChild(new Option("-- select connection --", ""));
    selectSink.appendChild(new Option("-- select connection --", ""));

    select.appendChild(new Option("file", "file"));

    const connections = get_all_connection_names();
    connections.forEach(name => {
        select.appendChild(new Option(name, name));
        selectSink.appendChild(new Option(name, name));
    });
}

// --------------------------------------------------
// FILENAME AUTO-UPDATE (client name / AVO ID)
// --------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    const clientInput = document.getElementById("client_name_input");
    const avoInput    = document.getElementById("avo_id_input");
    const filenameSelect = document.getElementById("filename");

    if (!clientInput || !filenameSelect) return;

    const options = filenameSelect.querySelectorAll("option[data-template]");

    const sanitize = (value) =>
        value.trim().toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_-]/g, "");

    const updateOptions = () => {
        const client = sanitize(clientInput.value);
        const avoId  = avoInput ? sanitize(avoInput.value) : "";

        options.forEach(option => {
            let result = option.dataset.template;
            result = result.replace(/{client}/g,  client || "{client}");
            result = result.replace(/{avo_id}/g,  avoId  || "{avo_id}");
            option.value       = result;
            option.textContent = result;
        });
    };

    clientInput.addEventListener("input", updateOptions);
    if (avoInput) avoInput.addEventListener("input", updateOptions);

    // Trigger once on load in case fields are pre-filled (back-to-edit)
    if (clientInput.value || (avoInput && avoInput.value)) {
        updateOptions();
    }
});

// --------------------------------------------------
// WIZARD STEPS
// --------------------------------------------------

let current_step = 0;
const steps = document.querySelectorAll(".form-step");

function show_step(index) {
    steps.forEach((step, i) => {
        step.classList.toggle("active", i === index);
    });
}

function nextStep() {
    if (current_step < steps.length - 1) {
        current_step++;

        if (current_step === 2) populate_source_connection_selector();
        if (current_step === 3) generate_sink_sources_list();
        if (current_step === 4) {
            generate_sink_transforms_list();
            _restore_sink_selects();
        }

        show_step(current_step);
    }
}

function prevStep() {
    if (current_step > 0) {
        current_step--;
        show_step(current_step);
    }
}

// Apply saved sink_file_name and sink_connection after reaching step 5
function _restore_sink_selects() {
    const data = window._restoredSinkData;
    if (!data) return;

    // Restore filename select (options have already been updated by updateOptions())
    const fileSelect = document.getElementById('filename');
    if (fileSelect && data['sink_file_name']) {
        fileSelect.value = data['sink_file_name'][0];
    }

    // Restore connection select (populated by populate_source_connection_selector())
    const connSelect = document.getElementById('sink_connection_selector');
    if (connSelect && data['sink_connection_selector']) {
        connSelect.value = data['sink_connection_selector'][0];
    }
}

// Initialize
show_step(current_step);

// --------------------------------------------------
// FORM RESTORATION (back-to-edit)
// --------------------------------------------------

async function restoreWizardData(data) {
    if (!data || Object.keys(data).length === 0) return;

    // Stash for use by sink list generators and _restore_sink_selects
    window._restoredSinkData = data;

    // ── Step 2: dynamic connections ────────────────────────────────
    // Map each connection type to its form-field prefix and how many
    // static blocks already exist in the HTML (only S3 has statics).
    const connConfig = [
        { type: 's3',        prefix: 's3',        staticCount: 2 },
        { type: 'database',  prefix: 'db',         staticCount: 0 },
        { type: 'ftp',       prefix: 'ftp',        staticCount: 0 },
        { type: 'http',      prefix: 'http',       staticCount: 0 },
        { type: 'snowflake', prefix: 'snowflake',  staticCount: 0 },
        { type: 'bigquery',  prefix: 'bigquery',   staticCount: 0 },
        { type: 'vpn',       prefix: 'vpn',        staticCount: 0 },
    ];

    for (const { type, prefix, staticCount } of connConfig) {
        const names = data[prefix + '_name[]'] || [];
        for (let i = staticCount; i < names.length; i++) {
            document.getElementById('blockType').value = type;
            await add_configuration();

            // The new block is the last child of the .two-columns wrapper
            const container = document.getElementById('block_' + type);
            const twoCol    = container.querySelector('.two-columns');
            if (!twoCol) continue;
            const lastBlock = twoCol.lastElementChild;
            if (!lastBlock) continue;

            // Fill every non-readonly, non-file input in the block
            lastBlock.querySelectorAll('input[name], select[name]').forEach(el => {
                if (el.readOnly || el.type === 'file') return;
                const vals = data[el.name];
                if (vals && vals[i] !== undefined) el.value = vals[i];
            });
        }
    }

    // ── Step 3: dynamic sources ────────────────────────────────────
    // Rebuild the connection selector now that connections are restored.
    populate_source_connection_selector();

    const sourceNames   = data['source_name[]']        || [];
    const sourceTypes   = data['source_type[]']        || [];
    const sourcePaths   = data['source_path[]']        || [];
    const sourceConns   = data['source_connection[]']  || [];
    const sourceOffsets = data['source_time_offset[]'] || [];

    // source_connection[] only contains entries for non-file sources
    // (file.html has no connection input so it's never submitted).
    let connIdx = 0;

    for (let i = 1; i < sourceNames.length; i++) {   // index 0 = mapper (static)
        const isFile = sourceTypes[i] === 'file';

        const sel = document.getElementById('source_connection_selector');
        if (sel) sel.value = isFile ? 'file' : (sourceConns[connIdx] || '');

        await add_source('blockSources');

        const container = document.getElementById('blockSources');
        const lastBlock = container.lastElementChild;
        if (!lastBlock) { if (!isFile) connIdx++; continue; }

        const nameEl   = lastBlock.querySelector('input[name="source_name[]"]');
        const pathEl   = lastBlock.querySelector('[name="source_path[]"]');
        const offEl    = lastBlock.querySelector('input[name="source_time_offset[]"]');
        const connEl   = lastBlock.querySelector('input[name="source_connection[]"]');

        if (nameEl) nameEl.value = sourceNames[i]  || '';
        if (pathEl) pathEl.value = sourcePaths[i]  || '';
        if (offEl  && sourceOffsets[i] !== undefined) offEl.value = sourceOffsets[i];
        if (connEl && !isFile) connEl.value = sourceConns[connIdx] || '';

        if (!isFile) connIdx++;
    }

    // ── Step 4: transforms ─────────────────────────────────────────
    const tNames = data['transform_name[]'] || [];
    const tTypes = data['transform_type[]'] || [];
    const tFiles = data['transform_file[]'] || [];

    for (let i = 0; i < tNames.length; i++) {
        add_transform();
        const container = document.getElementById('blockTransforms');
        const lastBlock = container.lastElementChild;
        if (!lastBlock) continue;

        const n = lastBlock.querySelector('input[name="transform_name[]"]');
        const t = lastBlock.querySelector('input[name="transform_type[]"]');
        const f = lastBlock.querySelector('input[name="transform_file[]"]');
        if (n) n.value = tNames[i] || '';
        if (t) t.value = tTypes[i] || '';
        if (f) f.value = tFiles[i] || '';
    }

    // Step 5 (sink) selects and checkboxes are restored lazily:
    // • checkboxes  → generate_sink_sources/transforms_list() reads window._restoredSinkData
    // • selects     → _restore_sink_selects() reads window._restoredSinkData
    // Both are called automatically when the user navigates to those steps.
}

// Run restoration on load if there is saved data
document.addEventListener("DOMContentLoaded", () => {
    if (typeof WIZARD_DATA !== 'undefined' && Object.keys(WIZARD_DATA).length > 0) {
        restoreWizardData(WIZARD_DATA);
    }
});
