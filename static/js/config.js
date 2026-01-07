let sourceCounter = 0;
const sourcesRegistry = {};
// This function adds a connection block input
function add_configuration() {
				const type = document.getElementById("blockType").value;
				const container = document.getElementById("block_" + type);

        // Create input block
				const block = document.createElement("div");
				block.className = "input-block";

				let html = "";

        // Add header once
				if (!container.querySelector("h4")) {
                    const header = document.createElement("h4");
                    header.textContent = `${type.charAt(0).toUpperCase() + type.slice(1)} Configuration`;
                    container.appendChild(header);
                }

//               Create / get two-columns wrapper
        let two_columns = container.querySelector(".two-columns");
        if (!two_columns) {
            two_columns = document.createElement("div");
            two_columns.className = "two-columns";
            container.appendChild(two_columns);
        }

        // Build fields
        switch (type) {
            case "s3":
                html = `
                    <label>Name:</label><input type="text" name="s3_name[]" placeholder="Name"><br>
                    <label>Type:</label><input type="text" name="s3_type[]" value="s3" readonly><br>
                    <label>Bucket:</label><input type="text" name="s3_bucket[]" placeholder="Bucket"><br>
                    <button type="button" class="remove-btn">Remove</button>
                `;
                break;

            case "database":
                html = `
                    <label>Name:</label><input type="text" name="db_name[]" placeholder="Name"><br>
                    <label>Type:</label>
                    <select name="db_type[]">
                        <option value="postgres">Postgres</option>
                        <option value="mssql">MSSQL</option>
                        <option value="mysql">MySQL</option>
                        <option value="oracle">Oracle</option>
                    </select><br>
                    <label>Host:</label><input type="text" name="db_host[]" placeholder="Host"><br>
                    <label>Port:</label><input type="number" name="db_port[]" placeholder="Port"><br>
                    <label>Username:</label><input type="text" name="db_username[]" placeholder="Username"><br>
                    <label>Password:</label><input type="password" name="db_password[]" placeholder="Password"><br>
                    <label>Database:</label><input type="text" name="db_database[]" placeholder="Database"><br>
                    <button type="button" class="remove-btn">Remove</button>
                `;
                break;

            case "ftp":
                html = `
                    <label>Name:</label><input type="text" name="ftp_name[]" placeholder="Name"><br>
                    <label>Type:</label>
                    <select name="ftp_type[]">
                        <option value="ftp">FTP</option>
                        <option value="sftp">SFTP</option>
                    </select><br>
                    <label>Host:</label><input type="text" name="ftp_host[]" placeholder="Host"><br>
                    <label>Port:</label><input type="number" name="ftp_port[]" placeholder="Port"><br>
                    <label>Username:</label><input type="text" name="ftp_username[]" placeholder="Username"><br>
                    <label>Password:</label><input type="password" name="ftp_password[]" placeholder="Password"><br>
                    <button type="button" class="remove-btn">Remove</button>
                `;
                break;

            case "vpn":
                html = `
                    <label>Name:</label><input type="text" name="vpn_name[]" placeholder="Name"><br>
                    <label>Type:</label><input type="text" name="vpn_type[]" value="vpn" readonly><br>
                    <label>Product:</label><input type="text" name="vpn_product[]" placeholder="Product"><br>
                    <label>User name:</label><input type="text" name="vpn_username[]" placeholder="Username"><br>
                    <label>Password:</label><input type="password" name="vpn_password[]" placeholder="Password"><br>
                    <label>Address:</label><input type="text" name="vpn_address[]" placeholder="address:port"><br>
                    <label>Server cert:</label><input type="text" name="vpn_servercert[]" placeholder="Server cert"><br>
                    <label>Hostnames:</label><input type="text" name="vpn_hostnames[]" placeholder="ip/port"><br>
                    <button type="button" class="remove-btn">Remove</button>
                `;
                break;

            default:
                html = `<p>Unknown type selected.</p>`;
        }

        block.innerHTML = html;

        // Append block into two-columns
        two_columns.appendChild(block);
        }


// This function get all connections name
function get_all_connection_names() {
    const names = [];
    document.querySelectorAll("input[name$='_name[]']").forEach(input => {
        if (input.value.trim()) names.push(input.value.trim());
    });
    return names;
}

// This function adds a source block input
function add_source(containerId) {
    const container = document.getElementById(containerId);
    const block = document.createElement("div");
    block.className = "input-block";

    const connections = get_all_connection_names();
    if (connections.length === 0) {
        alert("Please add at least one connection before adding sources.");
        return;
    }

    let connectionOptions = connections.map(name => `<option value="${name}">${name}</option>`).join("");

    sourceCounter++;
    const sourceId = `source_${sourceCounter}`;
    const sourceName = `Source ${sourceCounter}`;

    sourcesRegistry[sourceId] = sourceName;

    block.innerHTML = `
        <label>Name:</label><input type="text" name="source_name[]" placeholder="Source Name"><br>
        <label>Connection:</label>
        <select name="source_connection[]">${connectionOptions}</select><br>
        <label>Type:</label><input type="text" name="source_type[]" placeholder="Source Type"><br>
        <label>Path/File Name:</label><input type="text" name="source_path[]" placeholder="Path or File Name"><br>
        <button type="button" class="remove-btn">Remove</button>

    `;

    container.appendChild(block);

    // ---- Sink checkbox ----
    const checkboxDiv = document.createElement("div");
    checkboxDiv.className = "sink-source";
    checkboxDiv.dataset.sourceId = sourceId;

    checkboxDiv.innerHTML = `
        <label>
            <input type="checkbox" name="sink_sources[]" value="${sourceId}">
            ${sourceId}
        </label>
    `;

    document.getElementById("sink_sources").appendChild(checkboxDiv);
}

// This function add a transform block input
function add_transform() {
//    const container = document.getElementById(containerId);
    const container = document.getElementById("blockTransforms");
    const block = document.createElement("div");
    block.className = "input-block";

//    const connections = get_all_connection_names();
//    if (connections.length === 0) {
//        alert("Please add at least one connection before adding sources.");
//        return;
//    }
//
//    let connectionOptions = connections.map(name => `<option value="${name}">${name}</option>`).join("");

    block.innerHTML = `
        <label>Name:</label><input type="text" name="transform_name[]" placeholder="Transform Name"><br>
        <label>Type:</label><input type="text" name="transform_type[]" placeholder="Transform Type"><br>
        <label>File Name:</label><input type="text" name="transform_file[]" placeholder="File Name"><br>
        <button type="button" class="remove-btn">Remove</button>
    `;

    container.appendChild(block);
    update_sink_source_selector();
}


document.addEventListener("click", function (e) {
    if (e.target.classList.contains("remove-btn")) {
        e.target.closest(".input-block").remove();
    }
});

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


