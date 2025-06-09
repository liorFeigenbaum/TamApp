function addConnection() {
				const type = document.getElementById("blockType").value;
				const container = document.getElementById("blockContainer");

				const block = document.createElement("div");
				block.className = "input-block";

				let html = "";

				switch (type) {
						case "s3":
								html = `
										<h4>S3 Configuration</h4>
										<label>Name:</label><input type="text" name="s3_name[]" placeholder="Name"><br>
										<label>Type:</label><input type="text" name="s3_type[]" placeholder="Type"><br>
										<label>Bucket:</label><input type="text" name="s3_bucket[]" placeholder="Bucket"><br>
								`;
								break;

						case "database":
								html = `
										<h4>Database Configuration</h4>
										<label>Name:</label><input type="text" name="db_name[]" placeholder="Name"><br>
										<label>Type:</label><input type="text" name="db_type[]" placeholder="Type"><br>
										<label>Host:</label><input type="text" name="db_host[]" placeholder="Host"><br>
										<label>Port:</label><input type="number" name="db_port[]" placeholder="Port"><br>
										<label>Username:</label><input type="text" name="db_username[]" placeholder="Username"><br>
										<label>Password:</label><input type="password" name="db_password[]" placeholder="Password"><br>
										<label>Database:</label><input type="text" name="db_database[]" placeholder="Database"><br>
								`;
								break;

						case "ftp":
								html = `
										<h4>FTP Configuration</h4>
										<label>Name:</label><input type="text" name="ftp_name[]" placeholder="Name"><br>
										<label>Type:</label><input type="text" name="ftp_type[]" placeholder="Type"><br>
										<label>Host:</label><input type="text" name="ftp_host[]" placeholder="Host"><br>
										<label>Port:</label><input type="number" name="ftp_port[]" placeholder="Port"><br>
										<label>Username:</label><input type="text" name="ftp_username[]" placeholder="Username"><br>
										<label>Password:</label><input type="password" name="ftp_password[]" placeholder="Password"><br>
								`;
								break;

						default:
								html = `<p>Unknown type selected.</p>`;
				}

				block.innerHTML = html;
				container.appendChild(block);
		}