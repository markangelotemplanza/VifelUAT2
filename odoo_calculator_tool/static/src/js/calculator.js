/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, useRef, onWillStart, onWillUnmount } from "@odoo/owl";

class CalculatorTool extends Component {
    setup() {
        super.setup();
        this.state = useState({
            currentInput: '',
            currentOperator: '',
            result: 0,
            displayValue: '',
            dropdownVisible: false,
            position: { x: 0, y: 0 },
        });

        this.draggableRef = useRef("draggable");
        this.cleanupDraggable = null;

        // Bind methods to ensure 'this' context is preserved
        this.setupDraggable = this.setupDraggable.bind(this);
        this.handleKeyPress = this.handleKeyPress.bind(this);

        onWillStart(() => {
            // Add keydown event listener when component is mounted
            document.addEventListener('keydown', this.handleKeyPress);
        });

        onWillUnmount(() => {
            if (this.cleanupDraggable) {
                this.cleanupDraggable();
            }
            document.removeEventListener('keydown', this.handleKeyPress); // Remove key event listener
        });
    }

    setupDraggable() {
        const draggable = this.draggableRef.el;
        if (!draggable || !this.state.dropdownVisible) return;

        let isDragging = false;
        let startX, startY;

        const onMouseDown = (e) => {
            isDragging = true;
            startX = e.clientX - this.state.position.x;
            startY = e.clientY - this.state.position.y;
            draggable.style.cursor = 'grabbing';
        };

        const onMouseMove = (e) => {
            if (!isDragging) return;
            const newX = e.clientX - startX;
            const newY = e.clientY - startY;
            this.state.position.x = newX;
            this.state.position.y = newY;
            draggable.style.transform = `translate(${newX}px, ${newY}px)`;
        };

        const onMouseUp = () => {
            isDragging = false;
            draggable.style.cursor = 'grab';
        };

        draggable.addEventListener('mousedown', onMouseDown);
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);

        this.cleanupDraggable = () => {
            draggable.removeEventListener('mousedown', onMouseDown);
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };

        return this.cleanupDraggable;
    }

    onDropdownToggleClick() {
        this.state.dropdownVisible = !this.state.dropdownVisible;
        if (this.state.dropdownVisible) {
            setTimeout(() => this.setupDraggable(), 0);
        }
    }

    onNumberClick(number) {
        if (this.state.currentOperator !== '' && this.state.currentInput === '') {
            this.state.currentInput = number;
            this.state.displayValue += number;
        } else {
            this.state.currentInput += number;
            if (this.state.displayValue === '0' || this.state.displayValue === this.state.result.toString()) {
                this.state.displayValue = number;
            } else {
                this.state.displayValue += number;
            }
        }
    }

    onOperatorClick(operator) {
        if (this.state.currentInput !== '' || this.state.result !== 0) {
            if (this.state.currentOperator !== '') {
                this.state.result = this.calculate(this.state.result, parseFloat(this.state.currentInput), this.state.currentOperator);
            } else if (this.state.currentInput !== '') {
                this.state.result = parseFloat(this.state.currentInput);
            }
            this.state.currentInput = '';
            this.state.currentOperator = operator;
            this.state.displayValue = `${this.state.result} ${operator} `;
        } else if (operator === '-' && this.state.currentInput === '') {
            this.state.currentInput = '-';
            this.state.displayValue = '-';
        }
    }

    onEqualsClick() {
        if (this.state.currentInput !== '' || this.state.currentOperator !== '') {
            const secondOperand = this.state.currentInput !== '' ? parseFloat(this.state.currentInput) : this.state.result;
            this.state.result = this.calculate(this.state.result, secondOperand, this.state.currentOperator);
            this.state.displayValue = this.state.result.toString();
            this.state.currentInput = '';
            this.state.currentOperator = '';
        }
    }

    onClearClick() {
        this.state.result = 0;
        this.state.currentInput = '';
        this.state.currentOperator = '';
        this.state.displayValue = '';
    }

    calculate(num1, num2, operator) {
        switch (operator) {
            case '+': return num1 + num2;
            case '-': return num1 - num2;
            case '*': return num1 * num2;
            case '/': return num1 / num2;
            case '%': return (num1 / 100) * num2;
            default: return num2;
        }
    }

    onDecimalClick() {
        if (!this.state.currentInput.includes('.')) {
            this.state.currentInput += '.';
            this.state.displayValue = this.state.currentInput;
        }
    }

    onToggleSignClick() {
        if (this.state.currentInput !== '') {
            this.state.currentInput = this.state.currentInput.startsWith('-') 
                ? this.state.currentInput.substring(1) 
                : '-' + this.state.currentInput;
            this.state.displayValue = this.state.currentInput;
        }
    }

    handleKeyPress(event) {
        const key = event.key;

        if (!isNaN(key) && key !== ' ') {
            this.onNumberClick(key);
        } else if (['+', '-', '*', '/', '%'].includes(key)) {
            this.onOperatorClick(key);
        } else if (key === 'Enter' || key === '=') {
            this.onEqualsClick();
        } else if (key === 'Escape' || key === 'Backspace') {
            this.onClearClick();
        } else if (key === '.') {
            this.onDecimalClick();
        } else if (key === 'ArrowUp') {
            this.onToggleSignClick();
        }
    }
}

CalculatorTool.template = 'CalculatorTool';

export const calculatorItem = {
    Component: CalculatorTool,
};

registry.category("systray").add("calculator", calculatorItem);
