# ML Training Job - Quick Start

## 🚀 Run This Job in 3 Steps

### 1. Build the Image
```bash
cd examples/ml-training
docker build -t homie-ml-training:v1 .
```

### 2. Add to Homie
```bash
homie env create ml-demo homie-ml-training:v1
```

### 3. Run on Network
```bash
homie run train.py --env ml-demo
```

That's it! The job will:
- ✅ Run on the best available peer
- ✅ Train a multi-layer neural network
- ✅ Return model, results, and logs

## 📊 What You Get

After completion, you'll have:
- `model.pkl` - Trained scikit-learn model
- `results.json` - Metrics (accuracy: ~88%)
- `training.log` - Full training logs

## 🎯 Common Use Cases

```bash
# Run on peer with GPU
homie run train.py --env ml-demo --gpu

# Run on specific peer
homie run train.py --env ml-demo --peer bob

# Train longer
homie run train.py --env ml-demo -- --epochs 100

# Use random forest instead
homie run train.py --env ml-demo -- --model rf
```

## 📈 Check History

```bash
homie history              # See all jobs
homie history --stats      # See statistics
```

## 🌐 Share With Team

```bash
# Push to Docker Hub
docker tag homie-ml-training:v1 username/homie-ml-training:v1
docker push username/homie-ml-training:v1

# Team runs without building
homie run train.py --image username/homie-ml-training:v1
```

## 📚 More Info

- **Full documentation:** See `README.md`
- **Usage guide:** See `USAGE.md`
- **Project structure:** See file tree in `README.md`
