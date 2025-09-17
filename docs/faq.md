# FAQ / Troubleshooting

# SSHException: Server not in known_hosts
If you get an error like this:
```
An unknown error occured (SSHException)
Server 'example.com' not found in known_hosts
```

You need to add the server to your known_hosts file. You can do this by running:
```bash
ssh-keyscan -H example.com >> ~/.ssh/known_hosts
```
or simply by connecting to the server via SSH once.


!!! warning

    b4 can only authenticate using SSH keys. Make sure you have set up SSH keys for your server and that your public key is added to the `~/.ssh/authorized_keys` file on the server.
