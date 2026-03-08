### **14.2 CONTRIBUTING.md** - কন্ট্রিবিউশন গাইডলাইন
```markdown
# Contributing to AI Trading Ecosystem

First off, thank you for considering contributing to AI Trading Ecosystem! It's people like you that make this project such a great tool for the global trading community.

## 📋 Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Community](#community)

## 🤝 Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker 24.0+
- Git

### Development Setup

1. **Fork and clone the repository**
```bash
git clone https://github.com/your-username/ai-trading-ecosystem.git
cd ai-trading-ecosystem
```

2. **Add upstream remote**
```bash
git remote add upstream https://github.com/original/ai-trading-ecosystem.git
```

3. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

4. **Install dependencies**
```bash
# Backend
cd backend
pip install -r requirements/dev.txt

# Frontend
cd ../frontend
npm install
```

5. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your configuration
```

6. **Run database migrations**
```bash
cd backend
alembic upgrade head
```

7. **Start development servers**
```bash
# Terminal 1 - Backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2 - Frontend
cd frontend
npm run dev

# Terminal 3 - Workers
cd backend
celery -A workers.celery_app worker --loglevel=info
```

## 🔄 Development Workflow

### 1. Choose an Issue
- Look for issues labeled `good-first-issue` or `help-wanted`
- Comment on the issue to let others know you're working on it
- Ask questions if something is unclear

### 2. Create a Branch
```bash
# Update your fork
git checkout main
git pull upstream main
git push origin main

# Create feature branch
git checkout -b feature/amazing-feature
# or
git checkout -b fix/bug-fix
# or
git checkout -b docs/update-readme
```

### 3. Make Changes
- Write clean, maintainable code
- Add tests for new features
- Update documentation
- Follow coding standards

### 4. Commit Changes
```bash
# Stage changes
git add .

# Commit with conventional message
git commit -m "feat: add amazing new feature"
git commit -m "fix: resolve issue with order execution"
git commit -m "docs: update API documentation"
git commit -m "test: add unit tests for market data"
```

### 5. Keep Branch Updated
```bash
git fetch upstream
git rebase upstream/main
# or
git merge upstream/main
```

### 6. Run Tests
```bash
# Backend tests
cd backend
pytest tests/ -v

# Frontend tests
cd frontend
npm run test

# Linting
flake8 backend/
npm run lint
```

### 7. Push Changes
```bash
git push origin feature/amazing-feature
```

### 8. Create Pull Request
- Go to GitHub and create a Pull Request
- Fill out the PR template
- Link related issues
- Request review from maintainers

## 📝 Pull Request Process

### PR Checklist
- [ ] Tests pass locally and in CI
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] Commit messages follow convention
- [ ] Branch is up to date with main
- [ ] No merge conflicts

### PR Template
```markdown
## Description
Brief description of the changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Related Issues
Fixes #123
Closes #456

## Screenshots
(if applicable)

## Additional Notes
Any additional information
```

### Review Process
1. At least one maintainer review required
2. All CI checks must pass
3. Address review comments
4. Squash commits if necessary
5. Merge when approved

## 📐 Coding Standards

### Python (Backend)

#### Style Guide
- Follow PEP 8
- Use Black for formatting
- Use isort for import sorting
- Maximum line length: 100
- Use type hints

```python
from typing import Optional, List
from datetime import datetime

class Order:
    """Order model with type hints."""
    
    def __init__(
        self,
        symbol: str,
        quantity: float,
        price: Optional[float] = None
    ) -> None:
        self.symbol = symbol
        self.quantity = quantity
        self.price = price
        self.created_at = datetime.utcnow()
    
    def calculate_value(self) -> float:
        """Calculate order value."""
        return self.quantity * (self.price or 0.0)
```

#### Naming Conventions
- Classes: `CamelCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_CASE`
- Private methods: `_leading_underscore`

#### Documentation
```python
def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """
    Calculate Relative Strength Index.
    
    Args:
        prices: List of closing prices
        period: RSI period (default: 14)
    
    Returns:
        RSI value between 0 and 100
    
    Raises:
        ValueError: If insufficient data
    
    Example:
        >>> prices = [100, 101, 102, 101, 100]
        >>> rsi = calculate_rsi(prices)
        >>> print(rsi)
        45.67
    """
    pass
```

### JavaScript/TypeScript (Frontend)

#### Style Guide
- Use ESLint with Airbnb config
- Use Prettier for formatting
- Use TypeScript for type safety
- Functional components preferred

```typescript
import React, { useState, useEffect } from 'react';

interface PriceProps {
  symbol: string;
  initialPrice?: number;
}

export const PriceDisplay: React.FC<PriceProps> = ({
  symbol,
  initialPrice = 0
}) => {
  const [price, setPrice] = useState<number>(initialPrice);
  
  useEffect(() => {
    const ws = new WebSocket(`wss://api.example.com/ws/${symbol}`);
    ws.onmessage = (event) => setPrice(JSON.parse(event.data).price);
    return () => ws.close();
  }, [symbol]);
  
  return (
    <div className="price-display">
      <h3>{symbol}</h3>
      <p className="price">${price.toFixed(2)}</p>
    </div>
  );
};
```

#### Naming Conventions
- Components: `PascalCase`
- Functions/variables: `camelCase`
- Constants: `UPPER_CASE`
- CSS classes: `kebab-case`

## 🧪 Testing Guidelines

### Unit Tests
```python
# tests/unit/test_market.py
import pytest
from unittest.mock import Mock, patch

def test_get_ticker_success(client):
    response = client.get("/api/v1/market/ticker/BTCUSDT")
    assert response.status_code == 200
    assert "price" in response.json()

@pytest.mark.asyncio
async def test_websocket_connection():
    async with websocket_connect("/ws/market/BTCUSDT") as ws:
        data = await ws.receive_json()
        assert data["type"] == "ticker"
```

### Integration Tests
```python
# tests/integration/test_trading.py
def test_place_order_flow(client, auth_headers):
    # Create order
    order_data = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": 0.001,
        "price": 50000
    }
    response = client.post(
        "/api/v1/trading/orders",
        json=order_data,
        headers=auth_headers
    )
    assert response.status_code == 201
    order_id = response.json()["id"]
    
    # Get order
    response = client.get(
        f"/api/v1/trading/orders/{order_id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    
    # Cancel order
    response = client.delete(
        f"/api/v1/trading/orders/{order_id}",
        headers=auth_headers
    )
    assert response.status_code == 200
```

### Test Coverage
```bash
# Aim for 80%+ coverage
pytest --cov=. --cov-report=html

# Check coverage report
open htmlcov/index.html
```

## 📚 Documentation

### Docstrings
- Use Google style for Python
- Use JSDoc for JavaScript/TypeScript
- Include examples where helpful

### README Updates
- Keep README.md up to date
- Add feature documentation
- Include configuration examples
- Update API documentation

### API Documentation
- OpenAPI/Swagger for REST
- AsyncAPI for WebSocket
- Keep examples current

## 🌍 Community

### Communication Channels
- GitHub Issues: Bug reports, feature requests
- GitHub Discussions: Questions, ideas
- Discord: Real-time chat
- Twitter: Announcements

### Recognition
- Contributors added to README
- Significant contributions recognized
- Monthly contributor highlights

### Support
- Check existing issues first
- Provide minimal reproducible examples
- Be patient and respectful

## 📈 Release Process

### Versioning
- Follow Semantic Versioning (MAJOR.MINOR.PATCH)
- Document breaking changes
- Update changelog

### Release Checklist
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Changelog updated
- [ ] Version bumped
- [ ] Tag created
- [ ] GitHub release created
- [ ] Docker images built
- [ ] Deployed to staging
- [ ] Smoke tests passed

## 🎉 Thank You!

Your contributions make this project better for everyone. We appreciate your time and effort!

Remember:
- Be respectful and inclusive
- Focus on quality over quantity
- Help others learn
- Have fun!

---

<div align="center">
Made with ❤️ by the global trading community
</div>
```

---
