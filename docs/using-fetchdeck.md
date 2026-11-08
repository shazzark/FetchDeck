# Using FetchDeck for large downloads

FetchDeck queues direct HTTP, HTTPS, FTP, magnet, and `.torrent` links. Add a direct link or torrent in Downloads, choose the save folder, and let the task finish. You can pause, resume, or remove a task; removing it from the list keeps its files unless you choose the separate Recycle Bin action. Paused downloads can resume after FetchDeck reopens when the server supports resuming.

## Common downloads

- **GitHub release files:** Open the project's official GitHub Releases page and copy the URL of the asset you need. Release assets are ready-to-use files; the repository's **Source code** archives contain source and are not usually the installer or dataset. Check the publisher's checksum or signature when one is provided.
- **SDKs:** Use the SDK download page for the product you need and select the archive for your operating system and CPU architecture. Follow the vendor's setup instructions after downloading; FetchDeck only transfers the file.
- **Datasets:** Get the file URL from the dataset owner's official page. Review access conditions, license, version, and citation instructions before using or redistributing the data. For multi-file datasets, add each official file link to the queue.
- **Linux distributions:** Follow the distribution's official download page to obtain its `.torrent` file or magnet link. Check the published checksum or signature against the completed image. FetchDeck can seed a finished torrent according to its configured aria2 seeding limits.

Only download material you are allowed to access. Prefer links published by the project or data owner, and check the final file against official hashes when available.

## Troubleshooting

- **aria2 is unavailable:** Install aria2 and make `aria2c.exe` available on `PATH`, then restart FetchDeck.
- **A server refuses resume:** Some servers do not support byte-range (HTTP) or REST (FTP) resume. Restarting that task may require downloading it from the beginning.
- **A connection fails at zero bytes:** Check the link in a browser, confirm the server is reachable, and retry later. The server may require a login or signed URL that FetchDeck does not support.
- **The dashboard is disconnected:** Downloads continue independently. Reopen Dashboard from FetchDeck while the app is running; the local stats API exists only while the app is open.
- **A torrent has no peers:** Confirm the torrent came from the official source and leave it queued while peers are available. Tracker and DHT reachability depends on the network.
