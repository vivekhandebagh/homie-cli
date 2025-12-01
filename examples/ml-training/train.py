#!/usr/bin/env python3
"""
Multi-file ML Training Job for Homie Network

This demonstrates a complex ML project with:
- Multiple Python modules (src/model.py, src/data_loader.py, src/utils.py)
- Configuration files (configs/config.json)
- Training pipeline with logging
- Model saving and evaluation

Usage:
    # Run with default config
    python train.py

    # Run with custom config
    python train.py --config configs/custom_config.json

    # Run with custom parameters
    python train.py --epochs 100 --model mlp
"""

import argparse
import sys
from pathlib import Path

# Import our modules
from src.model import MultiLayerModel
from src.data_loader import DataLoader
from src.utils import TrainingLogger, load_config, save_results


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Train ML model on Homie network')
    parser.add_argument(
        '--config',
        default='configs/config.json',
        help='Path to config file (default: configs/config.json)'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        help='Number of training epochs (overrides config)'
    )
    parser.add_argument(
        '--model',
        choices=['mlp', 'rf'],
        help='Model type (overrides config)'
    )
    parser.add_argument(
        '--output-dir',
        default='.',
        help='Output directory for results (default: current dir)'
    )

    return parser.parse_args()


def main():
    """Main training pipeline."""
    args = parse_args()

    # Initialize logger
    logger = TrainingLogger(log_file=f'{args.output_dir}/training.log')
    logger.start()

    try:
        # Load configuration
        config = load_config(args.config)

        # Override with command line args
        if args.epochs:
            config['max_iter'] = args.epochs
            print(f"Overriding epochs to {args.epochs}")

        if args.model:
            config['model_type'] = args.model
            print(f"Overriding model type to {args.model}")

        # Stage 1: Load and preprocess data
        print("\n[Stage 1/4] Loading data...")
        data_loader = DataLoader(config)
        X, y = data_loader.load_data()

        # Split data
        X_train, X_test, y_train, y_test = data_loader.split_data(X, y)

        # Preprocess
        X_train, X_test = data_loader.preprocess(X_train, X_test)

        logger.log_metric('train_samples', len(X_train))
        logger.log_metric('test_samples', len(X_test))
        logger.log_metric('n_features', X_train.shape[1])

        # Stage 2: Initialize model
        print("\n[Stage 2/4] Initializing model...")
        model = MultiLayerModel(config)
        logger.log_metric('model_type', config['model_type'])

        # Stage 3: Train model
        print("\n[Stage 3/4] Training model...")
        model.train(X_train, y_train)

        # Stage 4: Evaluate model
        print("\n[Stage 4/4] Evaluating model...")
        results = model.evaluate(X_test, y_test)

        # Log results
        for key, value in results.items():
            logger.log_metric(key, value)

        # Save model
        model_path = f'{args.output_dir}/model.pkl'
        model.save(model_path)

        # Save results
        final_results = logger.finish()
        save_results(final_results, f'{args.output_dir}/results.json')

        print("\n✅ Training completed successfully!")
        print(f"\nOutputs:")
        print(f"  - Model: {model_path}")
        print(f"  - Results: {args.output_dir}/results.json")
        print(f"  - Logs: {args.output_dir}/training.log")

        return 0

    except Exception as e:
        print(f"\n❌ Training failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
