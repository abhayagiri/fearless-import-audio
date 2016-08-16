## Requirements

```
sudo apt-get install -y libtag1-dev python-dev sox virtualenv
```

```
brew install python --universal --framework
brew install taglib sox
pip install virtualenv
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
