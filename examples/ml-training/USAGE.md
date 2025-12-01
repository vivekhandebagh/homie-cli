# How to Run This ML Job on Homie Network

## Prerequisites

1. **Homie is set up and running:**
   ```bash
   # On your machine
   homie up

   # On your friend's machine (the one with GPU/more resources)
   homie up
   ```

2. **Both machines are on the same network and can see each other:**
   ```bash
   homie peers
   # Should show your friend's machine
   ```

## Step 1: Build the Docker Image

```bash
cd examples/ml-training
docker build -t homie-ml-training:v1 .
```

This creates a Docker image with:
- Python 3.11
- scikit-learn, numpy, pandas, matplotlib
- All your project files (src/, configs/, train.py)

## Step 2: Add Environment to Homie

```bash
homie env create ml-demo homie-ml-training:v1
homie env list  # Verify it was added
```

## Step 3: Run Training Job on the Network

### Basic Run (Auto-select best peer)
```bash
homie run train.py --env ml-demo
```

This will:
1. Find the best available peer
2. Send `train.py` to them
3. The peer pulls the `homie-ml-training:v1` image (if not cached)
4. Runs training in isolated container
5. Streams output back to you
6. Downloads results: `model.pkl`, `results.json`, `training.log`

### Run on Specific Peer
```bash
homie run train.py --env ml-demo --peer bob
```

### Run with GPU
```bash
homie run train.py --env ml-demo --gpu
```

### Custom Parameters
```bash
# Override epochs
homie run train.py --env ml-demo -- --epochs 100

# Change model type
homie run train.py --env ml-demo -- --model rf

# Multiple args
homie run train.py --env ml-demo -- --epochs 100 --model mlp
```

## Expected Output

You'll see streaming output like:

```
╭─ Sending to bob (best available) ────────────────────────────────╮
│ Job ID: a1b2c3d4                                                 │
│ Script: train.py                                                 │
╰──────────────────────────────────────────────────────────────────╯

[bob] ============================================================
[bob] Training started at 2025-12-01 00:32:17
[bob] ============================================================
[bob]
[bob] Loading config from configs/config.json
[bob]
[bob] [Stage 1/4] Loading data...
[bob] Generated 2000 samples with 30 features
[bob]
[bob] [Stage 2/4] Initializing model...
[bob]
[bob] [Stage 3/4] Training model...
[bob] Training mlp model...
[bob] Iteration 1, loss = 1.04640846
[bob] Iteration 2, loss = 0.90681991
...
[bob] Test accuracy: 0.8875
[bob]
[bob] Model saved to ./model.pkl
[bob] ✅ Training completed successfully!

╭─ Job Complete ─────────────────────────────────────────────────╮
│ Runtime: 1.1s                                                  │
│ Downloaded: model.pkl, results.json, training.log             │
╰────────────────────────────────────────────────────────────────╯
```

## Check Job History

```bash
# See all jobs you've run
homie history

# See jobs on specific peer
homie history --peer bob

# See only your sent jobs
homie history --role mooch

# See statistics
homie history --stats
```

## Sharing With Team

If you want your team to use this without building locally:

### Push to Docker Hub

```bash
# Tag with your username
docker tag homie-ml-training:v1 yourusername/homie-ml-training:v1

# Login to Docker Hub
docker login

# Push
docker push yourusername/homie-ml-training:v1
```

### Team Members Run Directly

```bash
# No build needed! Auto-pulls from Docker Hub
homie run train.py --image yourusername/homie-ml-training:v1
```

## Troubleshooting

**"Image not found" error?**
- Make sure you built the image: `docker images | grep homie-ml-training`
- Or use full image path: `homie run train.py --image homie-ml-training:v1`

**"No available peers" error?**
- Check peers are online: `homie peers`
- Make sure both machines are on same network
- Verify group secret matches on both machines

**Training fails with import errors?**
- Rebuild image: `docker build --no-cache -t homie-ml-training:v1 .`
- Check requirements.txt has all dependencies

**Peer doesn't have GPU green dot?**
- They need nvidia-docker installed
- Test: `docker run --rm --gpus all nvidia/cuda:12.1-base-ubuntu22.04 nvidia-smi`
