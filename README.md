# Blockchain CTF Challenge

This is a CTF challenge to learn something about Bitcoin like blockchains. The blockchain creates a simple cryptocurrency.

## Setup

Install the dependencies:

```
pip install -r requirements.txt
```

Start the challenge server:

```
./shop.py
```

## Instructions

Connect to the challenge on port 8327. This will open the flag shop. While the flag shop is open, you can connect with the blockchain client to the port shown by the flag shop:

```
./client.py <server_ip> <blockchain_node_port>
```

The client will start receiving blocks. To give commands to the client, connect to its RPC interface:

```
nc 127.0.0.1 7839
```

You will want to create an address, start mining to it to receive some money and then make some transactions, similar to this:

```
>> new_address
159c16d08380c847542b82fdf746858239d1f8e635c63608c37fa4cc58769908
>> start_mining 159c16d08380c847542b82fdf746858239d1f8e635c63608c37fa4cc58769908
>> show_wallet
159c16d08380c847542b82fdf746858239d1f8e635c63608c37fa4cc58769908: 500000
c39acdd838359259aae93b023307f2e502d7647842ead5d43d186b33105b7123: 0
>> send 7fcac4f6f2cf2e7f21a5991302858c229edf1e6cc19a39c7d80218dc8d26bce0 23423  
Transaction sent to miners.
```

Note that this client mined 500000 STC before checking the wallet, which might take you some time. The flag shop's node can mine 1024 times faster than the client to prevent a 51% attack, so you might want to find a faster way to get money.

Have fun!