// This function adds a connection block input
function add_configuration() {
				const type = document.getElementById("blockType").value;
				const container = document.getElementById("block_" + type);

				const block = document.createElement("div");
				block.className = "input-block";

				let html = "";

				if (container.childElementCount === 0) {
                    const header = document.createElement("h4");
                    header.textContent = `${type.charAt(0).toUpperCase() + type.slice(1)} Configuration`;
                    container.appendChild(header);
                }

				switch (type) {
						case    "s3":
								html = `
										<label>Name:</label><input type="text" name="s3_name[]" placeholder="Name"><br>
										<label>Type:</label><input type="text" name="s3_type[]" placeholder="Type"><br>
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
										    <option value="ftp">ftp</option>
										    <option value="sftp">sftp</option>
										<label>Host:</label><input type="text" name="ftp_host[]" placeholder="Host"><br>
										<label>Port:</label><input type="number" name="ftp_port[]" placeholder="Port"><br>
										<label>Username:</label><input type="text" name="ftp_username[]" placeholder="Username"><br>
										<label>Password:</label><input type="password" name="ftp_password[]" placeholder="Password"><br>
										<button type="button" class="remove-btn">Remove</button>
								`;
								break;

						default:
								html = `<p>Unknown type selected.</p>`;
				}

				block.innerHTML = html;
				container.appendChild(block);
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

    block.innerHTML = `
        <h4>Source</h4>
        <label>Name:</label><input type="text" name="source_name[]" placeholder="Source Name"><br>
        <label>Type:</label><input type="text" name="source_type[]" placeholder="Source Type"><br>
        <label>Connection:</label>
        <select name="source_connection[]">${connectionOptions}</select><br>
        <label>Path/File Name:</label><input type="text" name="source_path[]" placeholder="Path or File Name"><br>
    `;

    container.appendChild(block);
}

document.addEventListener("click", function (e) {
    if (e.target.classList.contains("remove-btn")) {
        e.target.closest(".input-block").remove();
    }
});
