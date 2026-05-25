import { DecoratorNode } from './deps.js';

class ImageNode extends DecoratorNode {
  static getType() { return 'image'; }

  static clone(node) {
    return new ImageNode(node.__src, node.__alt, node.__key);
  }

  constructor(src, alt, key, width, height) {
    super(key);
    this.__src = src;
    this.__alt = alt || '';
    this.__width = width || null;
    this.__height = height || null;
  }

  static importJSON(json) {
    return new ImageNode(json.src || '', json.alt || '', undefined, json.width || null, json.height || null);
  }

  exportJSON() {
    return { type: 'image', version: 1, src: this.__src, alt: this.__alt, width: this.__width, height: this.__height };
  }

  createDOM() {
    const img = document.createElement('img');
    img.src = this.__src;
    img.alt = this.__alt;
    img.className = 'lex-image';
    img.contentEditable = 'false';
    if (this.__width) img.style.width = this.__width;
    if (this.__height) img.style.height = this.__height;
    return img;
  }

  updateDOM(prevNode, dom) {
    if (prevNode.__src !== this.__src) dom.src = this.__src;
    if (prevNode.__alt !== this.__alt) dom.alt = this.__alt;
    if (prevNode.__width !== this.__width) dom.style.width = this.__width || '';
    if (prevNode.__height !== this.__height) dom.style.height = this.__height || '';
    return false;
  }

  setWidth(width) { this.__width = width; }
  setHeight(height) { this.__height = height; }
  getWidth() { return this.__width; }
  getHeight() { return this.__height; }

  decorate() { return null; }

  isInline() { return false; }
}

function $createImageNode(src, alt, width, height) {
  return new ImageNode(src, alt, undefined, width, height);
}

export { ImageNode, $createImageNode };
