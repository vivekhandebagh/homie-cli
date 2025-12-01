# Multi-File ML Training Example for Homie

This example demonstrates how to run a complex, multi-file machine learning project on the Homie network using Docker.

## Project Structure

```
ml-training/
├── Dockerfile              # Docker image definition
├── requirements.txt        # Python dependencies
├── train.py               # Main training script
├── configs/
│   └── config.json        # Training configuration
├── src/
│   ├── __init__.py
│   ├── model.py           # Model definition
│   ├── data_loader.py     # Data loading/preprocessing
│   └── utils.py           # Training utilities
└── data/                  # Data files (optional)
```

## Quick Start

### Option 1: Build Docker Image Locally

```bash
# 1. Build the Docker image
cd examples/ml-training
docker build -t homie-ml-training:v1 .

# 2. Test locally (optional)
docker run --rm homie-ml-training:v1

# 3. Add to Homie environments
homie env create ml-demo homie-ml-training:v1

# 4. Run on Homie network
homie run train.py --env ml-demo
```

### Option 2: Push to Docker Hub (Recommended for sharing)

```bash
# 1. Build and tag
docker build -t yourusername/homie-ml-training:v1 .

# 2. Push to Docker Hub
docker push yourusername/homie-ml-training:v1

# 3. Run on any Homie peer (will auto-pull)
homie run train.py --image yourusername/homie-ml-training:v1
```

### Option 3: Run with GPU

If your peer has GPU support:

```bash
# GPU-enabled training (requires nvidia-docker on peer)
homie run train.py --image yourusername/homie-ml-training:v1 --gpu
```

## Usage Examples

```bash
# Basic training with default config
homie run train.py --env ml-demo

# Custom parameters
homie run train.py --env ml-demo -- --epochs 100 --model mlp

# Run on specific peer
homie run train.py --env ml-demo --peer bob

# Run on peer with GPU
homie run train.py --env ml-demo --gpu

# Custom config file (if you modified it)
homie run train.py --env ml-demo -- --config configs/custom_config.json
```

## What This Example Does

1. **Loads Configuration** - Reads training parameters from `configs/config.json`
2. **Generates Dataset** - Creates synthetic classification data
3. **Preprocesses Data** - Normalizes features, splits train/test
4. **Trains Model** - Multi-layer neural network or random forest
5. **Evaluates** - Tests on held-out data
6. **Saves Outputs**:
   - `model.pkl` - Trained model
   - `results.json` - Metrics and scores
   - `training.log` - Training logs

## Outputs

After running, you'll get these files downloaded:

- `model.pkl` - Pickled scikit-learn model
- `results.json` - Training metrics (accuracy, time, etc.)
- `training.log` - Detailed training logs

## Customization

### Modify Configuration

Edit `configs/config.json`:

```json
{
  "model_type": "mlp",          // or "rf" for random forest
  "hidden_layers": [128, 64, 32],
  "max_iter": 50,
  "n_samples": 2000,
  "n_features": 30,
  "n_classes": 3
}
```

### Add Your Own Data

Replace the synthetic data generation in `src/data_loader.py` with:

```python
def load_data(self):
    import pandas as pd
    df = pd.read_csv('data/mydata.csv')
    X = df.drop('target', axis=1).values
    y = df['target'].values
    return X, y
```

Then rebuild the Docker image.

### Add More Dependencies

Edit `requirements.txt`:

```
numpy>=1.24.0
scikit-learn>=1.3.0
pandas>=2.0.0
torch>=2.0.0        # Add PyTorch
transformers>=4.30  # Add Hugging Face
```

Rebuild the image after adding dependencies.

## Benefits of This Approach

✅ **Reproducible** - Same environment every time
✅ **Shareable** - Push to Docker Hub, team can use
✅ **Fast** - Image pulled once, cached forever
✅ **Version Control** - Tag images (v1, v2, v3)
✅ **No Setup** - Peers don't install dependencies
✅ **Industry Standard** - Same as Kubernetes, AWS, etc.

## Troubleshooting

**Image not found?**
```bash
# Make sure image is accessible
docker pull yourusername/homie-ml-training:v1
```

**Import errors?**
```bash
# Rebuild with updated requirements
docker build --no-cache -t homie-ml-training:v1 .
```

**Out of memory?**
```bash
# Reduce dataset size in config.json
"n_samples": 500  # instead of 2000
```

## Next Steps

- Replace synthetic data with real datasets
- Add more sophisticated models (PyTorch, TensorFlow)
- Implement checkpointing for long-running jobs
- Add visualization outputs (plots, charts)
- Use GPU-enabled base images for deep learning
