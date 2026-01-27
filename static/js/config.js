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

        // Create a temporary div and append
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = html;

        // Append the template inside the two-columns wrapper
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

    // -----------------------------
    // Determine source type
    // -----------------------------

    let type = "file";

    if (selected_connection !== "file") {
        const all_inputs = document.querySelectorAll("input[name$='_name[]']");
        const input = Array.from(all_inputs).find(i => i.value === selected_connection);

        if (!input) {
            alert(`Connection "${selected_connection}" not found!`);
            return;
        }

        // Look for the type input inside the same block
        const parentBlock = input.closest(".input-block");

        const type_input =
            parentBlock.querySelector("input[name$='_type[]'], select[name$='_type[]']");

        let raw_type = type_input ? type_input.value : "unknown";

        // 🔥 NORMALIZATION STEP
        if (DATABASE_TYPES.includes(raw_type)) {
            type = "database";
        } else {
            type = raw_type;
        }
    }

    // -----------------------------
    // Fetch source template
    // -----------------------------
    try {
        const response = await fetch(`/static/source_blocks/${type}.html`);
        if (!response.ok) throw new Error("Template not found");

        const html = await response.text();
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = html;

        const block = tempDiv.firstElementChild;

        // Inject selected connection if needed
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
        <label>Name:</label><input type="text" name="transform_name[]" placeholder="Transform Name"><br>
        <label>Type:</label><input type="text" name="transform_type[]" placeholder="Transform Type"><br>
        <label>File Name:</label><input type="text" name="transform_file[]" placeholder="File Name"><br>
        <button type="button" class="remove-btn">Remove</button>
    `;

    container.appendChild(block);
}

// --------------------------------------------------
// SINKS GENERATOR
// --------------------------------------------------

document.getElementById("wizardForm").addEventListener("submit", (e) => {
    const sinkNameInput = document.querySelector("input[name='sink_name']");
    if (sinkNameInput && !sinkNameInput.value) {
        sinkNameInput.value = sinkNameInput.placeholder; // fallback to placeholder
    }
});

function generate_sink_sources_list() {

    const listContainer = document.getElementById("sink_sources_list");
    if (!listContainer) return;

    listContainer.innerHTML = "";

    // Loop through all sources
    document.querySelectorAll("input[name='source_name[]']").forEach((input, idx) => {
        const connectionInput = input.closest(".input-block").querySelector("input[name='source_connection[]']");
        const typeInput = input.closest(".input-block").querySelector("input[name='source_type[]']");

        const div = document.createElement("div");
        div.className = "sink-source-item";
        div.innerHTML = `
            <label>
                <input type="checkbox" name="sink_sources[]" value="${input.value}" >
                ${input.value}
            </label>
        `;

        listContainer.appendChild(div);
    });
}

function generate_sink_transforms_list() {

    const listContainer = document.getElementById("sink_transforms_list");
    if (!listContainer) return;

    listContainer.innerHTML = "";

    // Loop through all sources
    document.querySelectorAll("input[name='transform_name[]']").forEach((input, idx) => {
        const typeInput = input.closest(".input-block").querySelector("input[name='source_type[]']");

        const div = document.createElement("div");
        div.className = "sink-source-item";
        div.innerHTML = `
            <label>
                <input type="checkbox" name="sink_transform[]" value="${input.value}" >
                ${input.value}
            </label>
        `;

        listContainer.appendChild(div);
    });

}

// --------------------------------------------------
// REMOVE BUTTON (GLOBAL)
// ------------

document.addEventListener("click", function (e) {
    if (e.target.classList.contains("remove-btn")) {
        e.target.closest(".input-block").remove();
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

  // clear existing
  select.innerHTML = "";
  selectSink.innerHTML = "";

  // default option
  select.appendChild(new Option("-- select connection --", ""));
  selectSink.appendChild(new Option("-- select connection --", ""));

  // fixed "file" option
  select.appendChild(new Option("file", "file"));

  // dynamic connections
  const connections = get_all_connection_names();
  connections.forEach(name => {
    select.appendChild(new Option(name, name));
    selectSink.appendChild(new Option(name, name));
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const clientInput = document.getElementById("client_name_input");
  const avoInput = document.getElementById("avo_id_input");
  const filenameSelect = document.getElementById("filename");

  if (!clientInput || !filenameSelect) return;

  const options = filenameSelect.querySelectorAll("option[data-template]");

  const sanitize = (value) =>
    value
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "_")
      .replace(/[^a-z0-9_-]/g, "");

  const updateOptions = () => {
    const client = sanitize(clientInput.value);
    const avoId = avoInput ? sanitize(avoInput.value) : "";

    options.forEach(option => {
      let result = option.dataset.template;

      result = result.replace(/{client}/g, client || "{client}");
      result = result.replace(/{avo_id}/g, avoId || "{avo_id}");

      option.value = result;
      option.textContent = result;
    });
  };

  clientInput.addEventListener("input", updateOptions);
  if (avoInput) avoInput.addEventListener("input", updateOptions);
});

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
    if (current_step === 2) {
      populate_source_connection_selector();
    }

    if (current_step === 3) {
      generate_sink_sources_list();
    }

    if (current_step === 4) {
      generate_sink_transforms_list();
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

// Initialize
show_step(current_step);
