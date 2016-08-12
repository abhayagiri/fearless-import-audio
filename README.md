## Requirements

```
sudo apt-get install -y python-dev sox virtualenv
```

## Setup

```
virtualenv venv
venv/bin/pip install -r requirements.txt
cp config.yaml.example config.yaml
```

Edit `config.yaml`.

## Running

```
./start
```
