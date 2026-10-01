import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { AccessibilityWidget } from '@/components/accessibility/AccessibilityWidget';
beforeEach(()=>{localStorage.clear();document.documentElement.className='';});
describe('truthful accessibility preferences',()=>{
 it('does not activate unavailable OpenDyslexic or request a blocked stylesheet',()=>{
  localStorage.setItem('re-a11y-settings',JSON.stringify({dyslexicFont:true}));
  render(<AccessibilityWidget/>);
  expect(document.documentElement).not.toHaveClass('a11y-dyslexic');
  expect(document.getElementById('re-opendyslexic-font')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Open accessibility settings'}));
  expect(screen.getByText(/OpenDyslexic font is currently unavailable/)).toBeInTheDocument();
  expect(screen.queryByRole('switch',{name:/Dyslexia/})).toBeNull();
 });
 it('removes global launcher and panel while mobile modal navigation is open',()=>{
  render(<AccessibilityWidget/>);
  fireEvent.click(screen.getByRole('button',{name:'Open accessibility settings'}));
  act(()=>window.dispatchEvent(new CustomEvent('re:mobile-menu-state',{detail:{open:true}})));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.queryByRole('button',{name:'Open accessibility settings'})).toBeNull();
  act(()=>window.dispatchEvent(new CustomEvent('re:mobile-menu-state',{detail:{open:false}})));
  expect(screen.getByRole('button',{name:'Open accessibility settings'})).toBeInTheDocument();
 });
});
